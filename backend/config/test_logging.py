"""
서버 로그 공통 설정(config.settings의 LOGGING)과 비밀 값·개인정보 가림(config.log_masking)

- 앱 로거의 INFO는 남기고, 외부 라이브러리의 INFO(호출마다 찍히는 요청 로그)는 남기지 않는다.
- Django 오류 로그는 운영(DEBUG=0)에서도 출력 핸들러로 간다(개발 전용 필터가 없다).
- AI 사용량·번역 못 한 이름 로그는 기존 형식(메시지만)과 출력 위치를 유지해 일반 로그에 중복으로 찍히지 않는다.
- 일반 로그·요청 줄은 메시지·traceback·stack_info를 포함한 출력 전체에서 비밀 값·개인정보를 가린다.
  원본 예외는 바꾸지 않고, 예외 종류·파일·줄 번호는 남는다.
"""

import io
import logging
from contextlib import contextmanager
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

import accounts.views
from trips import ai_usage, untranslated

from .log_masking import MASK, MaskingFormatter, MaskingServerFormatter, mask_secrets

INVITE = "INVITESECRET777"
AUTH_TOKEN = "realtoken0123456789abcdef"
BODY_PASSWORD = "P@ss-SECRET-body-111"
API_KEY = "sk-ant-FAKE-KEY-000"
EMAIL = "leak.user@example.com"


def console_formatter():
    [handler] = logging.getLogger("django").handlers
    return handler.formatter


@contextmanager
def captured(logger_name):
    """설정된 일반 로그 Formatter로 실제 출력될 문자열을 받는다(테스트 중에는 콘솔 출력이 꺼져 있다)."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(console_formatter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)


class LoggingConfigTests(SimpleTestCase):
    def test_app_loggers_keep_info_and_libraries_stay_quiet(self):
        for name in ("trips.reservations.views", "guides.search", "accounts.phone"):
            with self.subTest(name=name):
                self.assertTrue(logging.getLogger(name).isEnabledFor(logging.INFO))
        for name in ("httpx", "anthropic", "urllib3", "sentence_transformers"):
            with self.subTest(name=name):
                self.assertFalse(logging.getLogger(name).isEnabledFor(logging.INFO))
                self.assertTrue(logging.getLogger(name).isEnabledFor(logging.WARNING))

    def test_django_errors_reach_the_masked_console_without_debug_only_filter(self):
        django_logger = logging.getLogger("django")
        self.assertFalse(django_logger.propagate)  # 루트로도 보내면 두 번 찍힌다
        [handler] = django_logger.handlers
        self.assertIn(handler, logging.getLogger().handlers)
        self.assertEqual(handler.filters, [])
        self.assertIsInstance(handler.formatter, MaskingFormatter)

    def test_request_lines_use_the_masking_server_formatter(self):
        [handler] = logging.getLogger("django.server").handlers
        self.assertIsInstance(handler.formatter, MaskingServerFormatter)

    def test_ai_usage_and_untranslated_logs_keep_their_own_format(self):
        usage_logger = logging.getLogger(ai_usage.LOGGER_NAME)
        self.assertFalse(usage_logger.propagate)
        [handler] = usage_logger.handlers
        self.assertIs(type(handler.formatter), logging.Formatter)  # 가림 Formatter가 아니다(JSON 한 줄 그대로)
        self.assertEqual(handler.formatter._fmt, "%(message)s")
        self.assertEqual(handler.stream.name, "<stdout>")
        self.assertEqual(settings.LOGGING["loggers"][ai_usage.LOGGER_NAME]["handlers"], ["ai_usage"])
        self.assertNotIn(untranslated.LOGGER_NAME, settings.LOGGING["loggers"])  # 파일 핸들러는 모듈이 직접 만든다


class MaskSecretsTests(SimpleTestCase):
    def test_each_kind_is_masked_and_keys_or_columns_are_kept(self):
        cases = {
            f"POST /api/v1/trips/invitations/{INVITE}/accept/ HTTP/1.1": "POST /api/v1/trips/invitations/***/accept/ HTTP/1.1",
            "GET /cb?code=4/0AbcD&state=xy&key=AIzaFAKE HTTP/1.1": "GET /cb?code=***&state=xy&key=*** HTTP/1.1",
            "GET /x?Token=abc&page=2": "GET /x?Token=***&page=2",
            f"Bearer {AUTH_TOKEN}": "Bearer ***",
            f"key={API_KEY} google=AIzaSyFAKEFAKEFAKEFAKEFAKE12": "key=*** google=***",
            "{'password': 'P@ss word!', 'name': 'kim'}": "{'password': '***', 'name': 'kim'}",
            '{"api_key": "abc123", "client_secret": "s3"}': '{"api_key": "***", "client_secret": "***"}',
            "password=hunter2 DJANGO_SECRET_KEY=xyz GOOGLE_PLACES_API_KEY: AIzaSyFAKE":
                "password=*** DJANGO_SECRET_KEY=*** GOOGLE_PLACES_API_KEY: ***",
            "DETAIL:  Key (username)=(dup.user@example.com) already exists.": "DETAIL:  Key (username)=(***) already exists.",
            "DETAIL:  Key (trip_id, name)=(3, a(b)c) already exists.": "DETAIL:  Key (trip_id, name)=(***) already exists.",
            'DETAIL:  Key (owner_id)=(42) is not present in table "auth_user".':
                'DETAIL:  Key (owner_id)=(***) is not present in table "auth_user".',
            "DETAIL:  Failing row contains (1, kim@example.com, null).": "DETAIL:  Failing row contains (***).",
            f"sent to {EMAIL}": "sent to ***",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(mask_secrets(text), expected)

    def test_ordinary_text_and_code_lines_are_untouched(self):
        for text in (
            "Unauthorized: /api/v1/auth/me/",
            "/api/v1/trips/3/invitations/ created",
            "max_tokens=16000 input_tokens: 12 cache_read_input_tokens=0",
            "Token expired, token validation failed",
            '    password = request.data["password"]',  # traceback의 코드 줄은 디버깅용으로 남긴다
            "status code=500 Key error",
        ):
            with self.subTest(text=text):
                self.assertEqual(mask_secrets(text), text)

    def test_one_message_with_many_secrets(self):
        record = logging.LogRecord(
            "trips.views", logging.ERROR, __file__, 1, "call failed: %s",
            (f"user={EMAIL} password={BODY_PASSWORD} Authorization: Bearer {AUTH_TOKEN} "
             f"url=/trips/invitations/{INVITE}/accept/?code=abc&key={API_KEY}",), None)
        output = MaskingFormatter("%(levelname)s %(name)s: %(message)s").format(record)
        for secret in (EMAIL, BODY_PASSWORD, AUTH_TOKEN, INVITE, API_KEY, "code=abc"):
            self.assertNotIn(secret, output)
        self.assertTrue(output.startswith("ERROR trips.views: call failed: user=*** password=***"))

    def test_stack_info_is_masked(self):
        record = logging.LogRecord("trips.views", logging.WARNING, __file__, 1, "slow", None, None,
                                   sinfo=f'Stack (most recent call last):\n  File "x.py", line 3, in f\n    call("?token={INVITE}")')
        output = MaskingFormatter("%(message)s").format(record)
        self.assertNotIn(INVITE, output)
        self.assertIn('File "x.py", line 3, in f', output)

    def test_server_request_line_is_masked(self):
        record = logging.LogRecord("django.server", logging.INFO, __file__, 1, '"%s" %s %s',
                                   (f"POST /api/v1/trips/invitations/{INVITE}/accept/?token=abc HTTP/1.1", "404", "58"), None)
        record.status_code = 404
        output = MaskingServerFormatter(fmt="[{server_time}] {message}", style="{").format(record)
        self.assertIn('"POST /api/v1/trips/invitations/***/accept/?token=*** HTTP/1.1" 404 58', output)


class ProductionErrorLogTests(TestCase):
    """테스트 실행은 Django 운영 설정과 같이 DEBUG=False다."""

    def test_unhandled_500_masks_the_exception_and_omits_body_headers_and_cookies(self):
        self.assertFalse(settings.DEBUG)
        raised = RuntimeError(f"failed for {EMAIL} /trips/invitations/{INVITE}/accept/ api_key={API_KEY}")

        def boom(view, request, *args, **kwargs):
            raise raised

        client = APIClient(raise_request_exception=False)
        client.cookies["sessionid"] = "sessSECRET999"
        with mock.patch.object(accounts.views.LoginView, "post", boom), captured("django.request") as out:
            response = client.post("/api/v1/auth/login/", {"email": "body.user@example.com", "password": BODY_PASSWORD},
                                   format="json", HTTP_AUTHORIZATION=f"Token {AUTH_TOKEN}")
        output = out.getvalue()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b"Traceback", response.content)
        for secret in (EMAIL, INVITE, API_KEY, BODY_PASSWORD, AUTH_TOKEN, "sessSECRET999", "body.user@example.com"):
            self.assertNotIn(secret, output)
        # 디버깅 정보는 남는다: 수준·로거·경로·예외 종류·파일·줄 번호
        self.assertIn("ERROR django.request: Internal Server Error: /api/v1/auth/login/", output)
        self.assertIn("RuntimeError: failed for *** /trips/invitations/***/accept/ api_key=***", output)
        self.assertRegex(output, r'File ".*test_logging\.py", line \d+, in boom')
        self.assertIn(EMAIL, str(raised))  # 원본 예외는 그대로

    def test_logger_exception_masks_db_constraint_values_but_keeps_columns(self):
        user_model = get_user_model()
        with captured("guides.search") as out:
            try:
                with transaction.atomic():
                    user_model.objects.create_user(username="dup.user@example.com", email="dup.user@example.com")
                    user_model.objects.create_user(username="dup.user@example.com", email="dup.user@example.com")
            except IntegrityError as exc:
                logging.getLogger("guides.search").exception("여행 정보 검색 실패")
                original = str(exc)
        output = out.getvalue()
        self.assertNotIn("dup.user@example.com", output)
        self.assertIn("Key (username)=(***) already exists.", output)
        self.assertIn("django.db.utils.IntegrityError", output)
        self.assertIn("ERROR guides.search: 여행 정보 검색 실패", output)
        self.assertIn("dup.user@example.com", original)  # 원본 예외 메시지는 바꾸지 않는다
