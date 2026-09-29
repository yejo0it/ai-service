"""
휴대폰 인증번호 발송·확인.

- 인증번호는 salted HMAC으로만 저장하고, 확인에 성공하면 서명된 verification_token을 돌려준다.
- 회원가입은 이 토큰으로 "이 번호를 인증했다"는 사실만 확인한다(번호 재입력 위조 방지).
- 실제 SMS 발송 사업자는 아직 연동하지 않았다. DEBUG에서는 로그로 남기고 응답에 인증번호를
  포함해 개발 중 확인할 수 있게 하며, 운영에서는 발송 불가(503)로 처리한다.
"""

import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import PhoneVerification

logger = logging.getLogger(__name__)

PHONE_PATTERN = re.compile(r"^01[016789]\d{7,8}$")
CODE_TTL = timedelta(minutes=3)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
# 인증을 마친 뒤 회원가입까지 허용하는 시간
TOKEN_MAX_AGE_SECONDS = 30 * 60
TOKEN_SALT = "accounts.phone-verification"


class PhoneVerificationError(Exception):
    """클라이언트에 그대로 보여줄 메시지와 HTTP 상태를 담는다."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _hash(phone, code):
    return salted_hmac(TOKEN_SALT, f"{phone}:{code}").hexdigest()


def _send_sms(phone, text):
    if settings.DEBUG:
        logger.warning("[SMS 미연동] %s <- %s", phone, text)
        return
    raise PhoneVerificationError("인증번호를 보낼 수 없어요. 잠시 후 다시 시도해 주세요.", 503)


def request_code(phone):
    """인증번호를 만들어 보낸다. DEBUG에서만 인증번호를 돌려준다."""
    latest = PhoneVerification.objects.filter(phone=phone).first()
    if latest and timezone.now() - latest.created_at < RESEND_COOLDOWN:
        raise PhoneVerificationError("잠시 후 다시 요청해 주세요.", 429)

    code = f"{secrets.randbelow(1_000_000):06d}"
    PhoneVerification.objects.create(
        phone=phone, code_hash=_hash(phone, code), expires_at=timezone.now() + CODE_TTL
    )
    _send_sms(phone, f"[PinRoute] 인증번호는 {code} 입니다.")
    return code if settings.DEBUG else None


def verify_code(phone, code):
    """인증번호가 맞으면 회원가입에 쓸 verification_token을 돌려준다."""
    verification = PhoneVerification.objects.filter(phone=phone, verified_at__isnull=True).first()
    if not verification or verification.expires_at < timezone.now():
        raise PhoneVerificationError("인증번호가 만료되었어요. 다시 요청해 주세요.")
    if verification.attempts >= MAX_ATTEMPTS:
        raise PhoneVerificationError("입력 횟수를 초과했어요. 인증번호를 다시 요청해 주세요.")

    verification.attempts += 1
    if not constant_time_compare(verification.code_hash, _hash(phone, code)):
        verification.save(update_fields=["attempts"])
        raise PhoneVerificationError("인증번호가 일치하지 않아요.")

    verification.verified_at = timezone.now()
    verification.save(update_fields=["attempts", "verified_at"])
    return signing.dumps({"phone": phone}, salt=TOKEN_SALT)


def verified_phone(token):
    """verification_token에서 인증된 번호를 꺼낸다. 만료·위조면 None."""
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except signing.BadSignature:
        return None
    return data.get("phone")
