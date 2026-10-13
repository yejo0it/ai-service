import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from . import phone as phone_verification
from .models import Profile

User = get_user_model()

# 영문·숫자·특수문자를 모두 포함한 8~20자 (공백 불가)
PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d\s])\S{8,20}$")
PASSWORD_RULE_MESSAGE = "비밀번호는 영문, 숫자, 특수문자를 모두 포함해 8~20자로 입력해 주세요."


def normalize_email(value):
    return value.strip().lower()


def email_taken(email):
    return User.objects.filter(email__iexact=email).exists() or User.objects.filter(
        username__iexact=email
    ).exists()


def phone_field():
    return serializers.RegexField(
        phone_verification.PHONE_PATTERN,
        error_messages={"invalid": "휴대폰 번호를 숫자만 정확히 입력해 주세요."},
    )


# 닉네임: 한글·영문·숫자·밑줄 2~12자 (공백 불가)
NICKNAME_PATTERN = re.compile(r"^[가-힣A-Za-z0-9_]{2,12}$")
NICKNAME_RULE_MESSAGE = "닉네임은 한글, 영문, 숫자, 밑줄(_)로 2~12자 입력해 주세요."


def nickname_taken(name, exclude_user=None):
    users = User.objects.filter(first_name__iexact=name)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    return users.exists()


def profile_of(user):
    """회원 부가 정보. 관리자 명령으로 만든 회원 등 Profile이 없으면 만든다."""
    try:
        return user.profile
    except Profile.DoesNotExist:
        return Profile.objects.create(user=user)


class UserSerializer(serializers.ModelSerializer):
    """
    로그인·가입 응답과 마이페이지 공통 회원 정보.
    - phone: 휴대폰 인증을 마친 번호만 저장되므로 값이 있으면 인증된 번호다.
    - avatar: 프로필 사진 경로(`/media/...`). 없으면 null.
    - has_password: 이메일 가입 회원인지(소셜 가입 회원은 비밀번호가 없어 이메일을 바꿀 수 없다).
    - password_updated_at: 비밀번호를 마지막으로 바꾼 날짜(YYYY-MM-DD). 바꾼 적이 없으면 가입일, 비밀번호가 없으면 null.
    """

    name = serializers.CharField(source="first_name")
    phone = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()
    password_updated_at = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "name", "phone", "avatar", "has_password", "password_updated_at")

    def get_phone(self, user):
        profile = getattr(user, "profile", None)
        return profile.phone if profile else ""

    def get_avatar(self, user):
        profile = getattr(user, "profile", None)
        return profile.avatar.url if profile and profile.avatar else None

    def get_has_password(self, user):
        return user.has_usable_password()

    def get_password_updated_at(self, user):
        if not user.has_usable_password():
            return None
        profile = getattr(user, "profile", None)
        changed_at = (profile.password_changed_at if profile else None) or user.date_joined
        return timezone.localdate(changed_at).isoformat()


class NicknameSerializer(serializers.Serializer):
    name = serializers.RegexField(NICKNAME_PATTERN, error_messages={"invalid": NICKNAME_RULE_MESSAGE})


class AvatarSerializer(serializers.Serializer):
    avatar = serializers.FileField(error_messages={"required": "사진을 골라 주세요."})


class PasswordCheckSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)


class EmailChangeRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password_ticket = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return normalize_email(value)


class EmailChangeConfirmSerializer(serializers.Serializer):
    email_token = serializers.CharField()


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return normalize_email(value)


class PhoneSerializer(serializers.Serializer):
    phone = phone_field()


class PhoneVerifySerializer(PhoneSerializer):
    code = serializers.RegexField(
        r"^\d{6}$", error_messages={"invalid": "인증번호 6자리를 입력해 주세요."}
    )


class VerifiedPhoneSerializer(serializers.Serializer):
    """휴대폰 인증(phone/verify)에서 받은 토큰이 이 번호의 것인지 확인한다."""

    phone = phone_field()
    phone_verification_token = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if phone_verification.verified_phone(attrs["phone_verification_token"]) != attrs["phone"]:
            raise serializers.ValidationError({"phone": "휴대폰 인증을 다시 진행해 주세요."})
        return attrs


class NewPasswordSerializer(serializers.Serializer):
    """가입·재설정 공통 새 비밀번호 검증. 흔한 비밀번호 등 Django 기본 규칙도 함께 검사한다."""

    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    def validate_password(self, value):
        if not PASSWORD_PATTERN.match(value):
            raise serializers.ValidationError(PASSWORD_RULE_MESSAGE)
        return value

    def validate_new_password(self, attrs, user):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "비밀번호가 일치하지 않아요."})
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc


class SignupSerializer(VerifiedPhoneSerializer, NewPasswordSerializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        email = normalize_email(value)
        if email_taken(email):
            raise serializers.ValidationError("이미 가입된 이메일이에요.")
        return email

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self.validate_new_password(attrs, User(username=attrs["email"], email=attrs["email"]))
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return normalize_email(value)


class FindIdSerializer(VerifiedPhoneSerializer):
    pass


class PasswordResetVerifySerializer(VerifiedPhoneSerializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return normalize_email(value)


class PasswordChangeSerializer(NewPasswordSerializer):
    current_password = serializers.CharField(write_only=True)


class PasswordResetConfirmSerializer(NewPasswordSerializer):
    reset_token = serializers.CharField(write_only=True)


class KakaoLoginSerializer(serializers.Serializer):
    code = serializers.CharField()
    redirect_uri = serializers.URLField()


class NaverLoginSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField()