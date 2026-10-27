"""
헬스체크 전용 엔드포인트(config.health)

- 로그인 없이 200을 돌려주고, 만료·잘못된 토큰이 있어도 401이 되지 않는다. DB 접속을 확인하고 쿼리는 보내지 않는다.
- DB에 연결할 수 없으면 503이고, 응답·로그에 예외 메시지(접속 정보 등)를 넣지 않는다.
- 정상 헬스체크는 경고 로그(django.request)도 요청 줄(django.server)도 남기지 않는다. 실패한 헬스체크와 다른 요청 줄은 남긴다.
- 로그인이 필요한 API는 그대로 401이다.
"""

import logging
from unittest import mock

from django.db import OperationalError
from django.test import TestCase
from rest_framework.test import APIClient

from . import health
from .health import HEALTH_PATH, QuietHealthCheckFilter


def server_record(request_line, status):
    record = logging.LogRecord("django.server", logging.INFO, __file__, 1, '"%s" %s %s', (request_line, str(status), "16"), None)
    record.status_code = status
    return record


class HealthEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_200_without_login_and_checks_the_database(self):
        with mock.patch("config.health._check_database", wraps=health._check_database) as checked, \
                self.assertNumQueries(0), self.assertNoLogs("django.request"):
            response = self.client.get(HEALTH_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})
        checked.assert_called_once_with()  # 실제 DB 접속 확인(ensure_connection)을 거쳤다

    def test_database_failure_is_503_without_the_error_message(self):
        error = OperationalError('connection to server at "db" (10.0.0.5), port 5432 failed: password authentication')
        with mock.patch("config.health._check_database", side_effect=error), \
                self.assertLogs("config.health", "WARNING") as logs, self.assertLogs("django.request", "WARNING"):
            response = self.client.get(HEALTH_PATH)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "database": "unavailable"})
        self.assertEqual(logs.output, ["WARNING:config.health:health check: database unavailable (OperationalError)"])
        for secret in ("10.0.0.5", "password", "5432"):
            self.assertNotIn(secret, response.content.decode())
            self.assertNotIn(secret, "\n".join(logs.output))

    def test_head_is_allowed(self):
        self.assertEqual(self.client.head(HEALTH_PATH).status_code, 200)

    def test_invalid_token_does_not_turn_it_into_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        self.assertEqual(self.client.get(HEALTH_PATH).status_code, 200)

    def test_only_safe_methods(self):
        self.assertEqual(self.client.post(HEALTH_PATH).status_code, 405)

    def test_authenticated_api_still_requires_login(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)


class QuietHealthCheckFilterTests(TestCase):
    def test_successful_health_checks_are_dropped(self):
        for line in (f"GET {HEALTH_PATH} HTTP/1.1", f"HEAD {HEALTH_PATH} HTTP/1.1"):
            with self.subTest(line=line):
                self.assertFalse(QuietHealthCheckFilter().filter(server_record(line, 200)))

    def test_failed_health_checks_and_other_requests_are_kept(self):
        for line, status in ((f"GET {HEALTH_PATH} HTTP/1.1", 503), (f"GET {HEALTH_PATH} HTTP/1.1", 404),
                             ("GET /api/v1/auth/me/ HTTP/1.1", 401), ("GET /api/v1/trips/ HTTP/1.1", 200),
                             (f"GET {HEALTH_PATH}?x=1 HTTP/1.1", 200)):
            with self.subTest(line=line, status=status):
                self.assertTrue(QuietHealthCheckFilter().filter(server_record(line, status)))

    def test_records_without_a_request_line_are_kept(self):
        record = logging.LogRecord("django.server", logging.INFO, __file__, 1, "Watching for file changes", None, None)
        self.assertTrue(QuietHealthCheckFilter().filter(record))

    def test_filter_is_attached_to_the_request_line_handler(self):
        [handler] = logging.getLogger("django.server").handlers
        self.assertEqual([type(f) for f in handler.filters], [QuietHealthCheckFilter])
