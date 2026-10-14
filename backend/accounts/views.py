from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import phone as phone_verification
from . import email_change, social
from .nickname import nickname_of, random_nickname, usable_nickname
from .avatar import AvatarError, make_avatar
from .password_reset import make_reset_token, user_from_reset_token
from .models import Profile, SocialAccount
from .serializers import (
    AvatarSerializer,
    EmailChangeConfirmSerializer,
    EmailChangeRequestSerializer,
    EmailSerializer,
    FindIdSerializer,
    KakaoLoginSerializer,
    LoginSerializer,
    NaverLoginSerializer,
    NicknameSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordCheckSerializer,
    PasswordResetVerifySerializer,
    PhoneSerializer,
    PhoneVerifySerializer,
    SignupSerializer,
    UserSerializer,
    VerifiedPhoneSerializer,
    email_taken,
    profile_of,
)

User = get_user_model()


def auth_response(user, status_code=status.HTTP_200_OK):
    """로그인·가입 공통 응답: API 토큰 + 회원 정보."""
    token, _ = Token.objects.get_or_create(user=user)
    return Response({"token": token.key, "user": UserSerializer(user).data}, status=status_code)


class AuthAPIView(APIView):
    """로그인 전에 호출하는 API. 세션 인증(CSRF)을 거치지 않고, IP당 요청 횟수를 제한한다."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class CheckEmailView(AuthAPIView):
    """`POST /api/v1/auth/check-email/` — 가입 가능한 이메일인지."""

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"available": not email_taken(serializer.validated_data["email"])})


class PhoneRequestView(AuthAPIView):
    """`POST /api/v1/auth/phone/request/` — 인증번호 발송."""

    throttle_scope = "sms"

    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            code = phone_verification.request_code(serializer.validated_data["phone"])
        except phone_verification.PhoneVerificationError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)

        data = {"expires_in": int(phone_verification.CODE_TTL.total_seconds())}
        if code:
            # SMS 미연동 상태의 개발 편의용. DEBUG에서만 내려간다.
            data["debug_code"] = code
        return Response(data)


class PhoneVerifyView(AuthAPIView):
    """`POST /api/v1/auth/phone/verify/` — 인증번호 확인 후 verification_token 발급."""

    def post(self, request):
        serializer = PhoneVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = phone_verification.verify_code(**serializer.validated_data)
        except phone_verification.PhoneVerificationError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return Response({"verification_token": token})


class SignupView(AuthAPIView):
    """`POST /api/v1/auth/signup/` — 이메일 회원가입. 가입과 동시에 로그인된다."""

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(
                username=data["email"], email=data["email"], password=data["password"]
            )
            Profile.objects.create(
                user=user, phone=data["phone"], nickname=data.get("name") or random_nickname()
            )
        return auth_response(user, status.HTTP_201_CREATED)


class LoginView(AuthAPIView):
    """`POST /api/v1/auth/login/` — 이메일 로그인."""

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "이메일 또는 비밀번호가 올바르지 않아요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return auth_response(user)


class MeView(APIView):
    """
    `GET /api/v1/auth/me/` — 토큰이 유효한지 확인하고 로그인한 회원 정보를 돌려준다(만료·폐기 시 401).
    `PATCH /api/v1/auth/me/` — 닉네임 변경 ({name}). 형식만 확인한다(중복은 허용).
    `DELETE /api/v1/auth/me/` — 회원 탈퇴. 만든 여행(일정·숙소·짐싸기 노트 포함)과 회원 정보·로그인을 모두 지운다.
      일행으로 참여한 다른 사람의 여행에서는 빠지기만 한다.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = NicknameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"]
        profile = profile_of(request.user)
        profile.nickname = name
        profile.save(update_fields=["nickname"])
        return Response(UserSerializer(request.user).data)

    def delete(self, request):
        user = request.user
        profile = getattr(user, "profile", None)
        avatar = profile.avatar.name if profile and profile.avatar else ""
        # 여행·일정·숙소·짐싸기 노트·일행 참여·소셜 연결·토큰은 FK CASCADE로 함께 지워진다.
        with transaction.atomic():
            user.delete()
        # 업로드한 사진 파일은 DB 삭제로 지워지지 않으므로 따로 지운다.
        if avatar:
            Profile._meta.get_field("avatar").storage.delete(avatar)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvatarView(APIView):
    """
    `POST /api/v1/auth/me/avatar/` (multipart, avatar) — 프로필 사진 변경. 이전 사진 파일은 지운다.
    `DELETE /api/v1/auth/me/avatar/` — 프로필 사진 삭제 (기본 아바타로 돌아간다).
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = AvatarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            image = make_avatar(serializer.validated_data["avatar"])
        except AvatarError as exc:
            return Response({"avatar": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        profile = profile_of(request.user)
        old = profile.avatar.name if profile.avatar else ""
        profile.avatar.save(image.name, image, save=True)
        if old:
            profile.avatar.storage.delete(old)
        return Response(UserSerializer(request.user).data)

    def delete(self, request):
        profile = profile_of(request.user)
        if profile.avatar:
            profile.avatar.delete(save=True)
        return Response(UserSerializer(request.user).data)


class EmailAccountMixin:
    """이메일 변경은 비밀번호가 있는 이메일 가입 회원만 할 수 있다."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]

    def social_account_error(self, user):
        if user.has_usable_password():
            return None
        return Response(
            {"detail": "소셜 로그인 계정은 이메일을 변경할 수 없어요."}, status=status.HTTP_400_BAD_REQUEST
        )


class EmailChangePasswordView(EmailAccountMixin, APIView):
    """`POST /api/v1/auth/me/email/password/` — 현재 비밀번호 확인 후 password_ticket(10분) 발급."""

    # 비밀번호 대입을 막는다.
    throttle_scope = "auth"

    def post(self, request):
        if error := self.social_account_error(request.user):
            return error
        serializer = PasswordCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["password"]):
            return Response({"password": ["비밀번호가 올바르지 않아요."]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"password_ticket": email_change.make_password_ticket(request.user)})


def send_email_change_link(user, new_email):
    """새 이메일로 인증 링크를 보내고 변경 대기 이메일로 둔다."""
    link = email_change.confirm_link(email_change.make_email_token(user, new_email))
    nickname = nickname_of(user)
    try:
        email_change.send_confirm_email(new_email, link, nickname)
    except email_change.EmailChangeError as exc:
        return Response({"detail": str(exc)}, status=exc.status_code)

    profile = profile_of(user)
    profile.pending_email = new_email
    profile.save(update_fields=["pending_email"])
    response = {"email": new_email, "expires_in": email_change.EMAIL_TOKEN_MAX_AGE}
    if settings.DEBUG:
        # 메일 발송 설정이 없는 개발 환경용. DEBUG에서만 내려간다.
        response["debug_link"] = link
    return Response(response)


class EmailChangeRequestView(EmailAccountMixin, APIView):
    """
    `POST /api/v1/auth/me/email/` — 새 이메일로 '변경 이메일 인증하기' 링크를 보낸다
    ({email, password_ticket}). 메일의 링크를 누르기 전까지 이메일은 바뀌지 않는다.
    `DELETE /api/v1/auth/me/email/` — 이메일 변경 취소. 이미 보낸 링크도 쓸 수 없게 된다.
    """

    throttle_scope = "email"

    def post(self, request):
        user = request.user
        if error := self.social_account_error(user):
            return error
        serializer = EmailChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not email_change.password_ticket_valid(data["password_ticket"], user):
            return Response(
                {"detail": "비밀번호 확인 시간이 지났어요. 처음부터 다시 진행해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if data["email"] == user.email:
            return Response({"email": ["지금 쓰는 이메일이에요."]}, status=status.HTTP_400_BAD_REQUEST)
        if email_taken(data["email"]):
            return Response({"email": ["이미 가입된 이메일이에요."]}, status=status.HTTP_400_BAD_REQUEST)
        return send_email_change_link(user, data["email"])

    def delete(self, request):
        profile = profile_of(request.user)
        profile.pending_email = ""
        profile.save(update_fields=["pending_email"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailChangeResendView(EmailAccountMixin, APIView):
    """`POST /api/v1/auth/me/email/resend/` — 변경 대기 중인 이메일로 인증 메일을 다시 보낸다."""

    throttle_scope = "email"

    def post(self, request):
        user = request.user
        if error := self.social_account_error(user):
            return error
        pending = profile_of(user).pending_email
        if not pending:
            return Response(
                {"detail": "변경 중인 이메일이 없어요. 처음부터 다시 진행해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if email_taken(pending):
            return Response({"email": ["이미 가입된 이메일이에요."]}, status=status.HTTP_400_BAD_REQUEST)
        return send_email_change_link(user, pending)


class EmailChangeConfirmView(EmailAccountMixin, APIView):
    """`POST /api/v1/auth/me/email/confirm/` — 메일 링크의 email_token으로 이메일 변경을 마친다."""

    throttle_scope = "auth"

    def post(self, request):
        user = request.user
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = profile_of(user)
        try:
            new_email = email_change.email_from_token(
                serializer.validated_data["email_token"], user, profile.pending_email
            )
        except email_change.EmailChangeError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        if email_taken(new_email):
            return Response(
                {"detail": "그 사이 다른 계정이 가입한 이메일이에요."}, status=status.HTTP_400_BAD_REQUEST
            )
        with transaction.atomic():
            # 이메일 가입 회원은 username도 이메일이다(로그인 아이디).
            user.email = user.username = new_email
            user.save(update_fields=["email", "username"])
            profile.pending_email = ""
            profile.save(update_fields=["pending_email"])
        return Response(UserSerializer(user).data)


class PasswordChangeView(APIView):
    """
    `POST /api/v1/auth/me/password/` — 비밀번호 변경 ({current_password, password, password_confirm}).
    가입과 같은 규칙(영문·숫자·특수문자 8~20자)을 적용하고, 현재 비밀번호와 같은 비밀번호는 거절한다.
    바꾸면 지금 기기를 포함한 모든 로그인(토큰)이 해제되어 새 비밀번호로 다시 로그인해야 한다.
    """

    permission_classes = [IsAuthenticated]
    # 현재 비밀번호 대입을 막는다.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        user = request.user
        if not user.has_usable_password():
            return Response(
                {"detail": "소셜 로그인 계정은 비밀번호를 변경할 수 없어요."}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not user.check_password(data["current_password"]):
            return Response(
                {"current_password": ["현재 비밀번호가 올바르지 않아요."]}, status=status.HTTP_400_BAD_REQUEST
            )
        if data["password"] == data["current_password"]:
            return Response(
                {"password": ["현재 비밀번호와 다른 비밀번호를 입력해 주세요."]}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer.validate_new_password(data, user)
        set_new_password(user, data["password"])
        Token.objects.filter(user=user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PhoneChangeView(APIView):
    """
    `POST /api/v1/auth/me/phone/` — 휴대폰 번호 변경 ({phone, phone_verification_token}).
    phone/request → phone/verify로 인증을 마친 번호만 저장한다.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifiedPhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = profile_of(request.user)
        profile.phone = serializer.validated_data["phone"]
        profile.save(update_fields=["phone"])
        return Response(UserSerializer(request.user).data)


class LogoutView(APIView):
    """`POST /api/v1/auth/logout/` — 서버의 API 토큰을 폐기한다. 이 회원의 모든 기기에서 로그아웃된다."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def email_accounts_with_phone(phone):
    """이 번호로 인증해 이메일로 가입한 회원들. 소셜 가입 회원은 비밀번호·번호가 없어 제외된다."""
    return User.objects.filter(profile__phone=phone, is_active=True).exclude(email="")


class FindIdView(AuthAPIView):
    """`POST /api/v1/auth/find-id/` — 휴대폰 인증을 마친 번호로 가입한 이메일 목록."""

    def post(self, request):
        serializer = FindIdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        users = email_accounts_with_phone(serializer.validated_data["phone"]).order_by("date_joined")
        return Response({"emails": [user.email for user in users if user.has_usable_password()]})


class PasswordResetVerifyView(AuthAPIView):
    """
    `POST /api/v1/auth/password-reset/verify/` — 이메일과 인증한 휴대폰이 같은 회원이면
    비밀번호 재설정 토큰(15분, 1회용)을 발급한다.
    """

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = email_accounts_with_phone(data["phone"]).filter(email__iexact=data["email"]).first()
        if user is None or not user.has_usable_password():
            return Response(
                {"detail": "입력한 이메일과 휴대폰 번호로 가입된 계정이 없어요."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"reset_token": make_reset_token(user)})


def set_new_password(user, password):
    """비밀번호를 바꾸고 마이페이지에 보여 줄 변경 시각을 남긴다."""
    with transaction.atomic():
        user.set_password(password)
        user.save(update_fields=["password"])
        profile = profile_of(user)
        profile.password_changed_at = timezone.now()
        profile.save(update_fields=["password_changed_at"])


class PasswordResetConfirmView(AuthAPIView):
    """`POST /api/v1/auth/password-reset/confirm/` — 새 비밀번호 저장. 기존 로그인은 모두 해제된다."""

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = user_from_reset_token(data["reset_token"])
        if user is None:
            return Response(
                {"detail": "재설정 시간이 지났어요. 처음부터 다시 진행해 주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.validate_new_password(data, user)
        set_new_password(user, data["password"])
        Token.objects.filter(user=user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def social_profile(provider, data):
    """인가 코드로 카카오·네이버 회원 정보를 받는다. 입력이 잘못되면 ValidationError, 실패하면 SocialAuthError."""
    if provider == SocialAccount.Provider.KAKAO:
        serializer = KakaoLoginSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return social.kakao_profile(**serializer.validated_data)
    serializer = NaverLoginSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return social.naver_profile(**serializer.validated_data)


def social_login(provider, profile):
    """
    연결된 계정이 있으면 로그인, 없으면 자동 가입한다.
    같은 이메일로 이미 가입한 회원이 있으면 계정을 임의로 합치지 않고 이메일 로그인을 안내한다.
    """
    account = SocialAccount.objects.filter(provider=provider, uid=profile.uid).first()
    if account:
        return auth_response(account.user)

    email = profile.email.strip().lower() if profile.email_verified else ""
    if email and email_taken(email):
        return Response(
            {"detail": "이미 이메일로 가입된 계정이에요. 이메일로 로그인해 주세요."},
            status=status.HTTP_409_CONFLICT,
        )

    with transaction.atomic():
        user = User.objects.create_user(
            username=f"{provider}_{profile.uid}", email=email
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        Profile.objects.create(user=user, nickname=usable_nickname(profile.name))
        SocialAccount.objects.create(user=user, provider=provider, uid=profile.uid)
    return auth_response(user, status.HTTP_201_CREATED)


class SocialLinkView(APIView):
    """
    마이페이지 계정 연동.
    `POST /api/v1/auth/me/social/{provider}/` — 인가 코드로 소셜 계정을 지금 계정에 연결한다
      (카카오 {code, redirect_uri} / 네이버 {code, state}). 다른 PinRoute 계정에 연결된 소셜 계정이면 409.
    `DELETE /api/v1/auth/me/social/{provider}/` — 연결 해제. 비밀번호가 없는 계정의 마지막 소셜 계정은
      로그인할 방법이 없어지므로 해제할 수 없다.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def get_provider(self, provider):
        return provider if provider in SocialAccount.Provider.values else None

    def post(self, request, provider):
        provider = self.get_provider(provider)
        if provider is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        user = request.user
        label = SocialAccount.Provider(provider).label
        if user.social_accounts.filter(provider=provider).exists():
            return Response({"detail": f"이미 {label} 계정이 연결되어 있어요."}, status=status.HTTP_409_CONFLICT)
        try:
            profile = social_profile(provider, request.data)
        except social.SocialAuthError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)

        linked = SocialAccount.objects.filter(provider=provider, uid=profile.uid).first()
        if linked:
            return Response(
                {"detail": f"이미 다른 PinRoute 계정에 연결된 {label} 계정이에요."}, status=status.HTTP_409_CONFLICT
            )
        SocialAccount.objects.create(user=user, provider=provider, uid=profile.uid)
        return Response(UserSerializer(user).data)

    def delete(self, request, provider):
        provider = self.get_provider(provider)
        if provider is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        user = request.user
        account = user.social_accounts.filter(provider=provider).first()
        if account is None:
            return Response(UserSerializer(user).data)
        if not user.has_usable_password() and user.social_accounts.count() == 1:
            return Response(
                {"detail": "다른 로그인 방법이 없어 연결을 해제할 수 없어요."}, status=status.HTTP_400_BAD_REQUEST
            )
        account.delete()
        return Response(UserSerializer(user).data)


class KakaoLoginView(AuthAPIView):
    """`POST /api/v1/auth/kakao/` — 카카오 인가 코드로 로그인/자동 가입."""

    def post(self, request):
        serializer = KakaoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = social.kakao_profile(**serializer.validated_data)
        except social.SocialAuthError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return social_login(SocialAccount.Provider.KAKAO, profile)


class NaverLoginView(AuthAPIView):
    """`POST /api/v1/auth/naver/` — 네이버 인가 코드로 로그인/자동 가입."""

    def post(self, request):
        serializer = NaverLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = social.naver_profile(**serializer.validated_data)
        except social.SocialAuthError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)
        return social_login(SocialAccount.Provider.NAVER, profile)
