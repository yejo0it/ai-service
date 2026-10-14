import uuid

from django.conf import settings
from django.db import models


def avatar_upload_to(instance, filename):
    """추측할 수 없는 파일 이름으로 저장한다 (회원 id·원래 파일 이름을 드러내지 않는다)."""
    return f"avatars/{uuid.uuid4().hex}.jpg"


class Profile(models.Model):
    """기본 User(username=email)에 붙는 회원 부가 정보."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="profile", on_delete=models.CASCADE
    )
    # 이메일 가입은 인증을 마친 번호만 저장한다. 소셜 가입은 비어 있을 수 있다.
    phone = models.CharField("휴대폰 번호", max_length=11, blank=True, default="")
    # 업로드한 사진은 accounts.avatar에서 정사각형 JPEG로 다시 만들어 저장한다(EXIF 위치 정보 제거).
    avatar = models.ImageField("프로필 사진", upload_to=avatar_upload_to, blank=True, default="")
    # 화면에 보이는 이름. 중복을 허용하고, 가입할 때 비워 두면 랜덤으로 만든다(accounts.nickname).
    nickname = models.CharField("닉네임", max_length=12, blank=True, default="")
    # 인증 메일을 보내 두고 아직 확인하지 않은 새 이메일. 취소하면 비워서 보낸 링크를 쓸 수 없게 한다.
    pending_email = models.EmailField("변경 대기 이메일", blank=True, default="")
    # 마이페이지 변경·비밀번호 재설정 시각. 비어 있으면 가입한 뒤로 바꾼 적이 없다(가입일로 표시).
    password_changed_at = models.DateTimeField("비밀번호 변경 시각", null=True, blank=True)

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
