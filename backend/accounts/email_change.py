"""
이메일(로그인 아이디) 변경.

1) 현재 비밀번호 확인 → password_ticket(10분) 발급
2) password_ticket + 새 이메일 → 새 이메일로 '변경 이메일 인증하기' 링크 발송
   링크: {FRONTEND_URL}/mypage?email_token=... (1시간)
3) 링크로 마이페이지에 들어오면 email_token으로 변경을 마친다.

변경 대기 중인 새 이메일은 Profile.pending_email에 둔다. 링크는 그 값과 같을 때만 쓸 수 있어서
[이메일 변경 취소]로 비우면 이미 보낸 링크도 쓸 수 없다. [인증메일 재전송]은 같은 이메일로 새 링크를 보낸다.
토큰에는 발급 당시의 현재 이메일도 담아 두어, 한 번 바꾸고 나면 같은 링크를 다시 쓸 수 없다(1회용).
실제 메일 발송은 EMAIL_* 환경변수(SMTP)로 설정한다. EMAIL_HOST가 없으면 개발(DEBUG)은 콘솔(백엔드 로그)로
보내고 응답에 링크를 포함해 개발 중 확인할 수 있게 하며, 운영은 발송 불가(503)로 처리한다.
"""

from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

PASSWORD_TICKET_SALT = "accounts.email-change.password"
PASSWORD_TICKET_MAX_AGE = 10 * 60
EMAIL_TOKEN_SALT = "accounts.email-change.email"
EMAIL_TOKEN_MAX_AGE = 60 * 60


class EmailChangeError(Exception):
    """클라이언트에 그대로 보여줄 메시지와 HTTP 상태를 담는다."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def make_password_ticket(user):
    return signing.dumps({"uid": user.pk}, salt=PASSWORD_TICKET_SALT)


def password_ticket_valid(ticket, user):
    try:
        data = signing.loads(ticket, salt=PASSWORD_TICKET_SALT, max_age=PASSWORD_TICKET_MAX_AGE)
    except signing.BadSignature:
        return False
    return data.get("uid") == user.pk


def make_email_token(user, new_email):
    return signing.dumps({"uid": user.pk, "from": user.email, "to": new_email}, salt=EMAIL_TOKEN_SALT)


def email_from_token(token, user, pending_email):
    """이 회원이 요청한 변경이면 새 이메일을 돌려준다. 만료·위조·취소·이미 쓴 링크면 EmailChangeError."""
    try:
        data = signing.loads(token, salt=EMAIL_TOKEN_SALT, max_age=EMAIL_TOKEN_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise EmailChangeError("인증 링크가 만료되었어요. 이메일 변경을 다시 요청해 주세요.") from exc
    except signing.BadSignature as exc:
        raise EmailChangeError("올바르지 않은 인증 링크예요.") from exc
    if data.get("uid") != user.pk:
        raise EmailChangeError("이메일 변경을 요청한 계정으로 로그인해 주세요.", 403)
    if data.get("from") != user.email or data.get("to") != pending_email:
        raise EmailChangeError("이미 사용했거나 취소된 인증 링크예요.")
    return data["to"]


def confirm_link(token):
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/mypage?{urlencode({'email_token': token})}"


def send_confirm_email(new_email, link, nickname):
    if not settings.DEBUG and not settings.EMAIL_HOST:
        raise EmailChangeError("인증 메일을 보낼 수 없어요. 잠시 후 다시 시도해 주세요.", 503)

    subject = "[PinRoute]이메일 인증"
    text = (
        f"안녕하세요. {nickname}님.\nPinRoute 입니다.\n\n"
        "계정 이메일 변경을 완료하시려면\n"
        f"등록하신 이메일 주소({new_email})의 인증이 필요합니다. "
        "아래 링크를 클릭하여 기존 계정으로 로그인 후 이메일 변경을 완료해주세요.\n\n"
        "PinRoute 회원 본인이 아니라면 이 메세지를 무시해 주시기 바랍니다.\n\n"
        f"변경 이메일 인증하기: {link}\n\n감사합니다."
    )
    html = f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#0f172a;font-size:14px;line-height:1.7">
  <p style="margin:0 0 16px">안녕하세요. {escape(nickname)}님.<br>PinRoute 입니다.</p>
  <p style="margin:0 0 16px;color:#334155">
    계정 이메일 변경을 완료하시려면<br>
    등록하신 이메일 주소(<b>{escape(new_email)}</b>)의 인증이 필요합니다.
    아래 버튼을 클릭하여 기존 계정으로 로그인 후 이메일 변경을 완료해주세요.
  </p>
  <p style="margin:0 0 24px;color:#64748b">PinRoute 회원 본인이 아니라면 이 메세지를 무시해 주시기 바랍니다.</p>
  <a href="{escape(link)}"
     style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;
            font-weight:600;padding:12px 20px;border-radius:12px">변경 이메일 인증하기</a>
  <p style="margin:24px 0 0">감사합니다.</p>
</div>"""
    message = EmailMultiAlternatives(subject, text, to=[new_email])
    message.attach_alternative(html, "text/html")
    try:
        message.send()
    except OSError as exc:
        raise EmailChangeError("인증 메일을 보내지 못했어요. 잠시 후 다시 시도해 주세요.", 503) from exc
