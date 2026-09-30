from django.conf import settings
from django.db import models


class Profile(models.Model):
    """기본 User(username=email)에 붙는 회원 부가 정보."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="profile", on_delete=models.CASCADE
    )
    # 이메일 가입은 인증을 마친 번호만 저장한다. 소셜 가입은 비어 있을 수 있다.
    phone = models.CharField("휴대폰 번호", max_length=11, blank=True, default="")

    class Meta:
        verbose_name = "회원 정보"
        verbose_name_plural = "회원 정보"

    def __str__(self) -> str:
        return self.user.username


class SocialAccount(models.Model):
    """카카오·네이버 계정과 User의 연결."""

    class Provider(models.TextChoices):
        KAKAO = "kakao", "카카오"
        NAVER = "naver", "네이버"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="social_accounts", on_delete=models.CASCADE
    )
    provider = models.CharField("제공자", max_length=10, choices=Provider.choices)
    uid = models.CharField("제공자 회원 ID", max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "소셜 계정"
        verbose_name_plural = "소셜 계정"
        constraints = [
            models.UniqueConstraint(fields=("provider", "uid"), name="unique_social_account")
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.uid}"


class PhoneVerification(models.Model):
    """휴대폰 인증번호 발송 이력. 인증번호는 해시로만 저장한다."""

    phone = models.CharField("휴대폰 번호", max_length=11, db_index=True)
    code_hash = models.CharField("인증번호 해시", max_length=128)
    attempts = models.PositiveSmallIntegerField("입력 시도 횟수", default=0)
    expires_at = models.DateTimeField("만료 시각")
    verified_at = models.DateTimeField("인증 시각", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "휴대폰 인증"
        verbose_name_plural = "휴대폰 인증"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.phone} ({self.created_at:%Y-%m-%d %H:%M})"
