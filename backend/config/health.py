"""
`GET /api/v1/health/` — 컨테이너 헬스체크(docker-compose.yml)용 엔드포인트.

- 로그인 없이 호출한다. 인증을 거치지 않고 사용자·설정 정보를 돌려주지 않는다.
  (예전에는 로그인이 필요한 /auth/me/를 불러 15초마다 401 응답과 4xx 경고 로그가 쌓였다.)
- 서버가 요청을 처리하고 DB에 접속되면 200 {"status": "ok", "database": "ok"}. 원시 SQL 없이 접속만 확인한다
  (CONN_MAX_AGE 기본값 0이라 요청이 끝나면 연결을 닫으므로, 헬스체크마다 새로 접속해 DB 상태를 본다).
  DB에 연결할 수 없으면 503 {"status": "error", "database": "unavailable"}이고, 로그에는 예외 종류만 남긴다
  (예외 메시지에는 접속 주소 같은 내부 정보가 들어갈 수 있어 응답·로그에 넣지 않는다).
- 정상 응답의 요청 줄은 15초마다 쌓이지 않게 개발 서버 요청 로그(django.server)에서 뺀다(QuietHealthCheckFilter).
  실패(4xx·5xx)한 헬스체크 요청은 그대로 남긴다.
"""

import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe

HEALTH_PATH = "/api/v1/health/"
logger = logging.getLogger(__name__)


def _check_database():
    connection.ensure_connection()


@require_safe
def health(request):
    try:
        _check_database()
    except DatabaseError as exc:
        logger.warning("health check: database unavailable (%s)", type(exc).__name__)
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})


class QuietHealthCheckFilter(logging.Filter):
    """django.server 요청 줄('"GET /api/v1/health/ HTTP/1.1" 200 16') 중 정상 헬스체크만 뺀다."""

    def filter(self, record):
        status = getattr(record, "status_code", None)
        args = record.args if isinstance(record.args, tuple) else ()
        parts = str(args[0]).split() if args else []
        path = parts[1] if len(parts) > 1 else ""
        return not (path == HEALTH_PATH and isinstance(status, int) and status < 400)
