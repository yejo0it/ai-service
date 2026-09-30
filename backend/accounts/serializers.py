import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from . import phone as phone_verification

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


class UserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="first_name")

    class Meta:
        model = User
        fields = ("id", "email", "name")


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


class PasswordResetConfirmSerializer(NewPasswordSerializer):
    reset_token = serializers.CharField(write_only=True)


class KakaoLoginSerializer(serializers.Serializer):
    code = serializers.CharField()
    redirect_uri = serializers.URLField()


class NaverLoginSerializer(serializers.Serializer):
    code = serializers.CharField()
    state = serializers.CharField()
