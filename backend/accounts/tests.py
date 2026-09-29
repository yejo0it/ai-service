from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Profile, SocialAccount
from .social import SocialProfile

User = get_user_model()
PASSWORD = "pinroute!2026"
PHONE = "01012345678"


class PhoneVerificationMixin:
    """DEBUG 응답의 인증번호로 휴대폰 인증을 마치고 verification_token을 받는다."""

    def setUp(self):
        # 요청 제한(throttle) 카운터가 테스트 사이에 이어지지 않게 한다.
        cache.clear()

    def verify_phone(self, phone=PHONE):
        response = self.client.post("/api/v1/auth/phone/request/", {"phone": phone})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(
            "/api/v1/auth/phone/verify/", {"phone": phone, "code": response.data["debug_code"]}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data["verification_token"]


@override_settings(DEBUG=True)
class EmailSignupTests(PhoneVerificationMixin, APITestCase):
    """이메일 중복 확인 → 휴대폰 인증 → 가입 → 로그인 흐름."""

    def signup(self, **overrides):
        payload = {
            "email": "Traveler@Example.com",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "phone": PHONE,
            "phone_verification_token": self.verify_phone(),
            **overrides,
        }
        return self.client.post("/api/v1/auth/signup/", payload)

    def test_signup_then_login(self):
        response = self.signup()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["email"], "traveler@example.com")
        self.assertTrue(response.data["token"])
        self.assertEqual(User.objects.get().profile.phone, PHONE)

        response = self.client.post(
            "/api/v1/auth/login/", {"email": "traveler@example.com", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["token"])

    def test_login_rejects_wrong_password(self):
        self.signup()
        response = self.client.post(
            "/api/v1/auth/login/", {"email": "traveler@example.com", "password": "wrong!2026a"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_check_email_reports_taken_email(self):
        response = self.client.post("/api/v1/auth/check-email/", {"email": "traveler@example.com"})
        self.assertTrue(response.data["available"])
        self.signup()
        response = self.client.post("/api/v1/auth/check-email/", {"email": "TRAVELER@example.com"})
        self.assertFalse(response.data["available"])

    def test_signup_rejects_weak_password(self):
        response = self.signup(password="password1", password_confirm="password1")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_signup_rejects_password_mismatch(self):
        response = self.signup(password_confirm="pinroute!2027")
        self.assertIn("password_confirm", response.data)

    def test_signup_rejects_token_for_other_phone(self):
        response = self.signup(phone_verification_token=self.verify_phone("01099998888"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_phone_verify_rejects_wrong_code(self):
        response = self.client.post("/api/v1/auth/phone/request/", {"phone": PHONE})
        wrong = "000000" if response.data["debug_code"] != "000000" else "111111"
        response = self.client.post("/api/v1/auth/phone/verify/", {"phone": PHONE, "code": wrong})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_phone_request_has_cooldown(self):
        self.client.post("/api/v1/auth/phone/request/", {"phone": PHONE})
        response = self.client.post("/api/v1/auth/phone/request/", {"phone": PHONE})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class SocialLoginTests(APITestCase):
    """카카오·네이버 프로필 조회는 모킹하고, 로그인/자동 가입 처리만 검증한다."""

    profile = SocialProfile(uid="42", email="kakao@example.com", email_verified=True, name="여행자")

    def setUp(self):
        cache.clear()

    def kakao_login(self):
        with mock.patch("accounts.views.social.kakao_profile", return_value=self.profile):
            return self.client.post(
                "/api/v1/auth/kakao/",
                {"code": "abc", "redirect_uri": "http://localhost:8002/auth/kakao/callback"},
            )

    def test_first_login_creates_user_then_logs_in(self):
        response = self.kakao_login()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["email"], "kakao@example.com")

        response = self.kakao_login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(SocialAccount.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_does_not_merge_into_existing_email_account(self):
        User.objects.create_user(username="kakao@example.com", email="kakao@example.com")
        response = self.kakao_login()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(SocialAccount.objects.exists())

    def test_naver_login(self):
        profile = SocialProfile(uid="n-1", email="", email_verified=False, name="네이버")
        with mock.patch("accounts.views.social.naver_profile", return_value=profile):
            response = self.client.post("/api/v1/auth/naver/", {"code": "abc", "state": "xyz"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["name"], "네이버")


@override_settings(DEBUG=True)
class AccountRecoveryTests(PhoneVerificationMixin, APITestCase):
    """아이디 찾기 · 비밀번호 재설정 · 로그아웃."""

    def setUp(self):
        super().setUp()
        user = User.objects.create_user(
            username="traveler@example.com", email="traveler@example.com", password=PASSWORD
        )
        Profile.objects.create(user=user, phone=PHONE)

    def reset_token(self, email="traveler@example.com"):
        return self.client.post(
            "/api/v1/auth/password-reset/verify/",
            {"email": email, "phone": PHONE, "phone_verification_token": self.verify_phone()},
        )

    def test_find_id_returns_email_for_verified_phone(self):
        response = self.client.post(
            "/api/v1/auth/find-id/",
            {"phone": PHONE, "phone_verification_token": self.verify_phone()},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["emails"], ["traveler@example.com"])

    def test_find_id_requires_phone_verification(self):
        response = self.client.post(
            "/api/v1/auth/find-id/", {"phone": PHONE, "phone_verification_token": "forged"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_password_then_login_with_new_password(self):
        token = self.reset_token().data["reset_token"]
        new_password = "newroute#2026"
        response = self.client.post(
            "/api/v1/auth/password-reset/confirm/",
            {"reset_token": token, "password": new_password, "password_confirm": new_password},
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        login = lambda password: self.client.post(  # noqa: E731
            "/api/v1/auth/login/", {"email": "traveler@example.com", "password": password}
        )
        self.assertEqual(login(PASSWORD).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(login(new_password).status_code, status.HTTP_200_OK)

        # 같은 재설정 토큰은 다시 쓸 수 없다.
        response = self.client.post(
            "/api/v1/auth/password-reset/confirm/",
            {"reset_token": token, "password": "again#2026a", "password_confirm": "again#2026a"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reset_password_rejects_unknown_email(self):
        response = self.reset_token(email="nobody@example.com")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_logout_revokes_token(self):
        token = self.client.post(
            "/api/v1/auth/login/", {"email": "traveler@example.com", "password": PASSWORD}
        ).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(
            self.client.post("/api/v1/auth/logout/").status_code, status.HTTP_204_NO_CONTENT
        )
        self.assertEqual(
            self.client.post("/api/v1/auth/logout/").status_code, status.HTTP_401_UNAUTHORIZED
        )
