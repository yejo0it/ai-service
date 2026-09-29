from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import phone as phone_verification
from . import social
from .models import Profile, SocialAccount
from .serializers import (
    EmailSerializer,
    KakaoLoginSerializer,
    LoginSerializer,
    NaverLoginSerializer,
    PhoneSerializer,
    PhoneVerifySerializer,
    SignupSerializer,
    UserSerializer,
    email_taken,
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
            Profile.objects.create(user=user, phone=data["phone"])
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
            username=f"{provider}_{profile.uid}", email=email, first_name=profile.name[:150]
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        Profile.objects.create(user=user)
        SocialAccount.objects.create(user=user, provider=provider, uid=profile.uid)
    return auth_response(user, status.HTTP_201_CREATED)


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
