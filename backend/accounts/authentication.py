"""
로그인 토큰 만료 정책. 기존 DRF 토큰(`Authorization: Token <key>`)을 그대로 쓰고 만료만 서버에서 검사한다.

- 절대 만료: 로그인(토큰 발급) 후 AUTH_ABSOLUTE_DAYS(기본 30일)가 지나면 활동과 관계없이 만료. 연장되지 않는다.
- 비활동 만료: 마지막 사용자 활동 후 AUTH_INACTIVITY_DAYS(기본 7일)가 지나면 만료.
- '사용자 활동'은 화면에서 사용자가 직접 조작한 직후의 요청만이다. 프런트가 그런 요청에 `X-User-Activity: 1`을 붙이고,
  이 헤더가 없는 요청(자동 새로고침·백그라운드 호출)은 인증은 되지만 비활동 시간을 늘리지 못한다.
- 시간은 모두 서버 시계 기준이다. 만료된 토큰은 삭제하고 401(code: session_expired)로 거부한다.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed

from .models import AuthSession

ACTIVITY_HEADER = "X-User-Activity"
ACTIVITY_META_KEY = "HTTP_X_USER_ACTIVITY"
EXPIRED_MESSAGE = "로그인 세션이 만료되었어요. 다시 로그인해 주세요."
EXPIRED_CODE = "session_expired"


def absolute_limit() -> timedelta:
    return timedelta(days=settings.AUTH_ABSOLUTE_DAYS)


def inactivity_limit() -> timedelta:
    return timedelta(days=settings.AUTH_INACTIVITY_DAYS)


def is_expired(token: Token, session: AuthSession, now=None) -> bool:
    now = now or timezone.now()
    return now - token.created >= absolute_limit() or now - session.last_active_at >= inactivity_limit()


def start_session(user) -> Token:
    """
    로그인·가입 때 호출한다. 자격 증명으로 로그인한 시점이 새 세션의 시작(절대 만료 기준)이다.
    만료된 토큰은 키를 다시 쓰지 않고 새로 만든다. 아직 유효한 토큰은 다른 기기와 공유하므로 키를 유지한다.
    """
    now = timezone.now()
    token = Token.objects.filter(user=user).first()
    if token is not None:
        session, _ = AuthSession.objects.get_or_create(token=token)
        if is_expired(token, session, now):
            token.delete()
            token = None
    if token is None:
        token = Token.objects.create(user=user)
    else:
        token.created = now
        token.save(update_fields=["created"])
    AuthSession.objects.update_or_create(token=token, defaults={"last_active_at": now})
    return token


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        # 이 정책 이전에 발급된 토큰(활동 기록 없음)은 지금을 마지막 활동으로 본다.
        session, _ = AuthSession.objects.get_or_create(token=token)
        if is_expired(token, session):
            token.delete()
            raise AuthenticationFailed({"detail": EXPIRED_MESSAGE, "code": EXPIRED_CODE})
        token.auth_session = session
        return user, token

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None and request.META.get(ACTIVITY_META_KEY) == "1":
            self.record_activity(result[1].auth_session)
        return result

    @staticmethod
    def record_activity(session: AuthSession) -> None:
        """사용자 활동이면 비활동 시간을 갱신한다(절대 만료 기준인 token.created는 바꾸지 않는다). 쓰기는 가끔만 한다."""
        now = timezone.now()
        if now - session.last_active_at >= timedelta(seconds=settings.AUTH_ACTIVITY_WRITE_SECONDS):
            AuthSession.objects.filter(pk=session.pk).update(last_active_at=now)
