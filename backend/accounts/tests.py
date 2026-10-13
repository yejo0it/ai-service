import shutil
import tempfile
from io import BytesIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
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

    def test_me_returns_user_until_token_is_revoked(self):
        token = self.client.post(
            "/api/v1/auth/login/", {"email": "traveler@example.com", "password": PASSWORD}
        ).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "traveler@example.com")

        self.client.post("/api/v1/auth/logout/")
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_token(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)


def image_upload(name="photo.png", size=(800, 600), fmt="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, "skyblue").save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(DEBUG=True, MEDIA_ROOT=MEDIA_ROOT)
class MyPageTests(PhoneVerificationMixin, APITestCase):
    """마이페이지 기본정보: 닉네임·프로필 사진·이메일·휴대폰 변경"""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="traveler@example.com", email="traveler@example.com", password=PASSWORD
        )
        Profile.objects.create(user=self.user, phone=PHONE)
        self.client.force_authenticate(self.user)

    def test_me_shows_basic_info(self):
        data = self.client.get("/api/v1/auth/me/").data
        self.assertEqual(
            (data["email"], data["name"], data["phone"], data["avatar"], data["has_password"]),
            ("traveler@example.com", "", PHONE, None, True),
        )

    def test_change_nickname_checks_format_and_duplicates(self):
        User.objects.create_user(username="other@example.com", email="other@example.com", first_name="여행자")
        check = lambda name: self.client.post("/api/v1/auth/me/check-name/", {"name": name})
        self.assertFalse(check("여행자").data["available"])
        self.assertTrue(check("핀루트_1").data["available"])
        self.assertEqual(check("a").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(check("공백 있음").status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(self.client.patch("/api/v1/auth/me/", {"name": "여행자"}).status_code,
                         status.HTTP_400_BAD_REQUEST)
        response = self.client.patch("/api/v1/auth/me/", {"name": "핀루트_1"})
        self.assertEqual(response.data["name"], "핀루트_1")
        # 내 닉네임은 그대로 쓸 수 있다.
        self.assertTrue(check("핀루트_1").data["available"])

    def test_change_avatar_replaces_old_file(self):
        response = self.client.post("/api/v1/auth/me/avatar/", {"avatar": image_upload()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first = Profile.objects.get(user=self.user).avatar
        self.assertTrue(response.data["avatar"].startswith("/media/avatars/"))
        with Image.open(first.path) as saved:
            self.assertEqual((saved.format, saved.size), ("JPEG", (512, 512)))

        self.client.post("/api/v1/auth/me/avatar/", {"avatar": image_upload("b.jpg", fmt="JPEG")},
                         format="multipart")
        self.assertFalse(first.storage.exists(first.name))

    def test_avatar_rejects_non_image(self):
        fake = SimpleUploadedFile("photo.png", b"not an image", content_type="image/png")
        response = self.client.post("/api/v1/auth/me/avatar/", {"avatar": fake}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Profile.objects.get(user=self.user).avatar)

    def email_token(self, email="new@example.com"):
        """비밀번호 확인 → 새 이메일로 인증 메일 발송 → 메일 속 링크의 email_token"""
        ticket = self.client.post("/api/v1/auth/me/email/password/", {"password": PASSWORD}).data["password_ticket"]
        response = self.client.post("/api/v1/auth/me/email/", {"email": email, "password_ticket": ticket})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return parse_qs(urlparse(response.data["debug_link"]).query)["email_token"][0]

    def test_email_change_password_step(self):
        url = "/api/v1/auth/me/email/password/"
        self.assertEqual(self.client.post(url, {"password": "wrong"}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.client.post(url, {"password": PASSWORD}).data["password_ticket"])
        # 비밀번호 확인 없이(잘못된 티켓으로)는 메일을 보낼 수 없다.
        response = self.client.post("/api/v1/auth/me/email/", {"email": "new@example.com", "password_ticket": "x"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_change_sends_link_then_confirms(self):
        token = self.email_token("New@Example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        self.assertEqual(mail.outbox[0].subject, "[PinRoute]이메일 인증")
        self.assertIn("안녕하세요. traveler님.", mail.outbox[0].body)
        self.assertIn("등록하신 이메일 주소(new@example.com)", mail.outbox[0].body)
        self.assertIn("변경 이메일 인증하기", mail.outbox[0].alternatives[0][0])
        self.assertIn("http://localhost:8002/mypage?email_token=", mail.outbox[0].body)
        # 링크를 누르기 전에는 바뀌지 않는다.
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "traveler@example.com")

        response = self.client.post("/api/v1/auth/me/email/confirm/", {"email_token": token})
        self.assertEqual(response.data["email"], "new@example.com")
        # 같은 링크는 다시 쓸 수 없다.
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post("/api/v1/auth/me/email/confirm/", {"email_token": token}).status_code,
                         status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(None)
        login = self.client.post("/api/v1/auth/login/", {"email": "new@example.com", "password": PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_email_change_rejects_taken_email_and_other_user(self):
        User.objects.create_user(username="taken@example.com", email="taken@example.com")
        ticket = self.client.post("/api/v1/auth/me/email/password/", {"password": PASSWORD}).data["password_ticket"]
        response = self.client.post("/api/v1/auth/me/email/", {"email": "taken@example.com", "password_ticket": ticket})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        token = self.email_token()
        other = User.objects.create_user(username="other@example.com", email="other@example.com", password=PASSWORD)
        self.client.force_authenticate(other)
        response = self.client.post("/api/v1/auth/me/email/confirm/", {"email_token": token})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_email_change_resend_and_cancel(self):
        token = self.email_token()
        response = self.client.post("/api/v1/auth/me/email/resend/")
        self.assertEqual(response.data["email"], "new@example.com")
        self.assertEqual(len(mail.outbox), 2)

        # 취소하면 이미 보낸 링크도 쓸 수 없고, 다시 보낼 수도 없다.
        self.assertEqual(self.client.delete("/api/v1/auth/me/email/").status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.post("/api/v1/auth/me/email/confirm/", {"email_token": token}).status_code,
                         status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post("/api/v1/auth/me/email/resend/").status_code,
                         status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.get(pk=self.user.pk).email, "traveler@example.com")

    def test_social_account_cannot_change_email(self):
        social_user = User.objects.create_user(username="kakao_1", email="")
        social_user.set_unusable_password()
        social_user.save()
        self.client.force_authenticate(social_user)
        response = self.client.post("/api/v1/auth/me/email/password/", {"password": "x"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_avatar(self):
        self.client.post("/api/v1/auth/me/avatar/", {"avatar": image_upload()}, format="multipart")
        saved = Profile.objects.get(user=self.user).avatar
        response = self.client.delete("/api/v1/auth/me/avatar/")
        self.assertIsNone(response.data["avatar"])
        self.assertFalse(saved.storage.exists(saved.name))

    def test_change_phone_requires_verification(self):
        new_phone = "01098765432"
        url = "/api/v1/auth/me/phone/"
        self.assertEqual(self.client.post(url, {"phone": new_phone, "phone_verification_token": "x"}).status_code,
                         status.HTTP_400_BAD_REQUEST)
        token = self.verify_phone(new_phone)
        response = self.client.post(url, {"phone": new_phone, "phone_verification_token": token})
        self.assertEqual(response.data["phone"], new_phone)


class AuthThrottleTests(APITestCase):
    """로그인 전 인증 API는 IP당 요청 횟수를 제한한다(auth: 30/min)."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_login_is_throttled(self):
        payload = {"email": "nobody@example.com", "password": "wrong"}
        codes = [self.client.post("/api/v1/auth/login/", payload).status_code for _ in range(31)]
        self.assertEqual(codes[:30], [status.HTTP_400_BAD_REQUEST] * 30)
        self.assertEqual(codes[30], status.HTTP_429_TOO_MANY_REQUESTS)
