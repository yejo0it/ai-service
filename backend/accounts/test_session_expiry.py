"""
로그인 만료 정책 테스트: 비활동 7일 · 로그인 후 30일(절대).
시간은 저장된 시각(토큰 created, 마지막 활동)을 과거로 돌려 흉내 낸다(서버 시계 기준 검사).
"""

import importlib
from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from .models import AuthSession

User = get_user_model()
PASSWORD = "pinroute!2026"
ME = "/api/v1/auth/me/"
ACTIVITY = {"HTTP_X_USER_ACTIVITY": "1"}


class SessionExpiryTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="a@example.com", email="a@example.com", password=PASSWORD)
        self.key = self.login()

    def login(self):
        response = APIClient().post("/api/v1/auth/login/", {"email": "a@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["token"]

    def call(self, key=None, **extra):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {key or self.key}")
        return client.get(ME, **extra)

    def token(self):
        return Token.objects.get(user=self.user)

    def set_times(self, created_ago=None, active_ago=None):
        now = timezone.now()
        if created_ago is not None:
            Token.objects.filter(user=self.user).update(created=now - created_ago)
        if active_ago is not None:
            AuthSession.objects.filter(token__user=self.user).update(last_active_at=now - active_ago)

    def last_active_ago(self):
        return timezone.now() - AuthSession.objects.get(token__user=self.user).last_active_at

    # --- 비활동 만료 ---
    def test_fresh_login_works(self):
        self.assertEqual(self.call().status_code, status.HTTP_200_OK)

    def test_expires_after_7_days_without_activity(self):
        self.set_times(active_ago=timedelta(days=7, minutes=1))
        response = self.call()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "session_expired")
        self.assertFalse(Token.objects.filter(key=self.key).exists())  # 만료된 토큰은 삭제된다
        self.assertEqual(self.call().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_not_expired_just_before_7_days(self):
        self.set_times(active_ago=timedelta(days=6, hours=23, minutes=59))
        self.assertEqual(self.call().status_code, status.HTTP_200_OK)

    def test_user_activity_refreshes_inactivity_timer(self):
        self.set_times(active_ago=timedelta(days=6))
        created = self.token().created
        self.assertEqual(self.call(**ACTIVITY).status_code, status.HTTP_200_OK)
        self.assertLess(self.last_active_ago(), timedelta(minutes=1))
        self.assertEqual(self.token().created, created)  # 절대 만료 기준은 그대로

    def test_background_calls_do_not_extend_inactivity(self):
        self.set_times(active_ago=timedelta(days=6))
        for _ in range(5):  # 활동 표시가 없는 자동 호출
            self.assertEqual(self.call().status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(self.last_active_ago(), timedelta(days=6))
        # 그대로 7일이 지나면 만료된다.
        self.set_times(active_ago=timedelta(days=7, minutes=1))
        self.assertEqual(self.call().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_activity_writes_are_throttled(self):
        self.set_times(active_ago=timedelta(seconds=10))
        self.call(**ACTIVITY)
        self.assertGreaterEqual(self.last_active_ago(), timedelta(seconds=10))  # 60초 안에는 다시 쓰지 않는다

    # --- 절대 만료 ---
    def test_expires_30_days_after_login_even_if_active(self):
        self.set_times(created_ago=timedelta(days=30, minutes=1), active_ago=timedelta(seconds=1))
        response = self.call(**ACTIVITY)  # 방금까지 계속 활동했어도
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "session_expired")

    def test_not_expired_just_before_30_days(self):
        self.set_times(created_ago=timedelta(days=29, hours=23), active_ago=timedelta(seconds=1))
        self.assertEqual(self.call(**ACTIVITY).status_code, status.HTTP_200_OK)

    def test_activity_cannot_extend_the_30_day_limit(self):
        self.set_times(created_ago=timedelta(days=29, hours=23, minutes=59), active_ago=timedelta(days=6))
        created = self.token().created
        self.assertEqual(self.call(**ACTIVITY).status_code, status.HTTP_200_OK)
        self.assertEqual(self.token().created, created)  # 활동이 로그인 시각을 미루지 못한다
        self.set_times(created_ago=timedelta(days=30, minutes=1))
        self.assertEqual(self.call(**ACTIVITY).status_code, status.HTTP_401_UNAUTHORIZED)

    # --- 만료 뒤 / 재로그인 ---
    def test_relogin_after_expiry(self):
        self.set_times(created_ago=timedelta(days=31))
        self.assertEqual(self.call().status_code, status.HTTP_401_UNAUTHORIZED)
        new_key = self.login()
        self.assertNotEqual(new_key, self.key)
        self.assertEqual(self.call(new_key).status_code, status.HTTP_200_OK)
        self.assertEqual(self.call(self.key).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_key_is_not_reused_on_login(self):
        self.set_times(active_ago=timedelta(days=8))  # 만료됐지만 서버에 요청한 적은 없다
        new_key = self.login()
        self.assertNotEqual(new_key, self.key)
        self.assertEqual(self.call(self.key).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.call(new_key).status_code, status.HTTP_200_OK)

    def test_login_while_valid_keeps_key_and_starts_new_window(self):
        self.set_times(created_ago=timedelta(days=20), active_ago=timedelta(days=3))
        self.assertEqual(self.login(), self.key)  # 다른 기기와 공유하는 토큰은 유지
        self.assertLess(timezone.now() - self.token().created, timedelta(minutes=1))  # 자격 증명 로그인은 새 세션
        self.assertLess(self.last_active_ago(), timedelta(minutes=1))

    def test_logout_still_works(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.key}")
        self.assertEqual(client.post("/api/v1/auth/logout/").status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.call().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_api_ignores_expired_header(self):
        # 로그인 API는 토큰 검사를 거치지 않으므로, 만료된 토큰이 헤더에 남아 있어도 로그인할 수 있다.
        self.set_times(created_ago=timedelta(days=40))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.key}")
        response = client.post("/api/v1/auth/login/", {"email": "a@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- 설정 / 기존 토큰 / CORS ---
    @override_settings(AUTH_INACTIVITY_DAYS=1, AUTH_ABSOLUTE_DAYS=2)
    def test_limits_come_from_settings(self):
        self.set_times(active_ago=timedelta(days=1, minutes=1))
        self.assertEqual(self.call().status_code, status.HTTP_401_UNAUTHORIZED)
        key = self.login()
        self.set_times(created_ago=timedelta(days=2, minutes=1), active_ago=timedelta(seconds=1))
        self.assertEqual(self.call(key, **ACTIVITY).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_without_session_record_works(self):
        AuthSession.objects.all().delete()  # 정책 이전에 발급된 토큰
        self.assertEqual(self.call().status_code, status.HTTP_200_OK)
        self.assertTrue(AuthSession.objects.filter(token__user=self.user).exists())

    def test_cors_allows_activity_header(self):
        response = APIClient().options(
            ME, HTTP_ORIGIN="http://localhost:8002", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-user-activity",
        )
        self.assertIn("x-user-activity", response["Access-Control-Allow-Headers"])


class ExistingTokenMigrationTests(APITestCase):
    def test_existing_tokens_start_a_session_at_deploy(self):
        migration = importlib.import_module("accounts.migrations.0008_start_sessions_for_existing_tokens")
        user = User.objects.create_user(username="old@example.com")
        token = Token.objects.create(user=user)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(days=200))
        migration.start_sessions(apps, None)
        token.refresh_from_db()
        self.assertLess(timezone.now() - token.created, timedelta(minutes=1))
        self.assertLess(timezone.now() - AuthSession.objects.get(token=token).last_active_at, timedelta(minutes=1))
