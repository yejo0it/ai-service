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
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from trips.models import PackingItem, Trip, TripMember

from .models import PhoneVerification, Profile, SocialAccount
from .nickname import ADJECTIVES, ANIMALS, NICKNAME_PATTERN, nickname_of, random_nickname
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

    def test_concurrent_duplicate_signup_is_a_400_not_a_db_error(self):
        # 다른 요청이 먼저 가입시킨 상황: 중복 검사는 통과했지만 저장할 때 DB 제약에 걸린다.
        User.objects.create_user(username="traveler@example.com", email="traveler@example.com")
        with mock.patch("accounts.serializers.email_taken", return_value=False):
            response = self.signup()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"email": ["이미 가입된 이메일이에요."]})
        self.assertEqual(User.objects.count(), 1)

    def test_signup_with_nickname(self):
        response = self.signup(name="핀루트_1")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["name"], "핀루트_1")
        self.assertEqual(User.objects.get().profile.nickname, "핀루트_1")

    def test_signup_without_nickname_creates_random_and_keeps_it_on_login(self):
        for payload in ({}, {"name": ""}):
            User.objects.all().delete()
            PhoneVerification.objects.all().delete()
            cache.clear()
            response = self.signup(**payload)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            nickname = User.objects.get().profile.nickname  # DB에 저장됨
            self.assertTrue(NICKNAME_PATTERN.match(nickname))
            self.assertEqual(response.data["user"]["name"], nickname)

            for _ in range(2):  # 로그인할 때마다 새로 만들지 않는다.
                login = self.client.post(
                    "/api/v1/auth/login/", {"email": "traveler@example.com", "password": PASSWORD}
                )
                self.assertEqual(login.data["user"]["name"], nickname)
            self.assertEqual(User.objects.get().profile.nickname, nickname)

    def test_signup_rejects_bad_nickname(self):
        response = self.signup(name="a!b")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.exists())

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

    def test_dev_sms_notice_logs_no_phone_number_or_code(self):
        with self.assertLogs("accounts.phone", "WARNING") as logs:
            response = self.client.post("/api/v1/auth/phone/request/", {"phone": PHONE})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        output = "\n".join(logs.output)
        for secret in (PHONE, PHONE[-4:], response.data["debug_code"]):
            self.assertNotIn(secret, output)
        self.assertIn("[SMS 미연동]", output)


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

    def test_concurrent_first_login_logs_into_the_account_the_other_request_created(self):
        # 다른 요청이 먼저 같은 소셜 계정으로 가입시킨 상황: 첫 조회에서는 계정이 없었다.
        other = User.objects.create_user(username="kakao_42", email="kakao@example.com")
        SocialAccount.objects.create(user=other, provider="kakao", uid="42")
        real_filter = SocialAccount.objects.filter
        lookups = []

        def first_lookup_misses(*args, **kwargs):
            lookups.append(kwargs)
            return SocialAccount.objects.none() if len(lookups) == 1 else real_filter(*args, **kwargs)

        with mock.patch("accounts.views.email_taken", return_value=False), \
                mock.patch.object(SocialAccount.objects, "filter", side_effect=first_lookup_misses):
            response = self.kakao_login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], other.id)
        self.assertEqual((User.objects.count(), SocialAccount.objects.count()), (1, 1))

    def test_signup_conflict_without_a_linked_account_is_a_409(self):
        User.objects.create_user(username="kakao_42")  # 같은 이름의 사용자만 있고 소셜 연결은 없다
        with mock.patch("accounts.views.email_taken", return_value=False):
            response = self.kakao_login()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data, {"detail": "소셜 로그인에 실패했어요. 다시 시도해 주세요."})
        self.assertFalse(SocialAccount.objects.exists())

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

    def test_social_name_outside_nickname_rule_becomes_random(self):
        profile = SocialProfile(uid="n-2", email="", email_verified=False, name="홍 길동 (Hong)")
        with mock.patch("accounts.views.social.naver_profile", return_value=profile):
            response = self.client.post("/api/v1/auth/naver/", {"code": "abc", "state": "xyz"})
        self.assertTrue(NICKNAME_PATTERN.match(response.data["user"]["name"]))
        self.assertNotIn("홍", response.data["user"]["name"])


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
        Profile.objects.create(user=self.user, phone=PHONE, nickname="여행자")
        self.client.force_authenticate(self.user)

    def test_me_shows_basic_info(self):
        data = self.client.get("/api/v1/auth/me/").data
        self.assertEqual(
            (data["email"], data["name"], data["phone"], data["avatar"], data["has_password"]),
            ("traveler@example.com", "여행자", PHONE, None, True),
        )

    def test_change_nickname_saves_to_profile_and_allows_duplicates(self):
        other = User.objects.create_user(username="other@example.com", email="other@example.com")
        Profile.objects.create(user=other, nickname="핀루트_1")
        response = self.client.patch("/api/v1/auth/me/", {"name": "핀루트_1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "핀루트_1")
        self.assertEqual(Profile.objects.get(user=self.user).nickname, "핀루트_1")
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["name"], "핀루트_1")

    def test_change_nickname_trims_outer_spaces_and_keeps_inner_space(self):
        response = self.client.patch("/api/v1/auth/me/", {"name": "  여행하는 고래 "})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "여행하는 고래")
        self.assertEqual(Profile.objects.get(user=self.user).nickname, "여행하는 고래")

    def test_nickname_error_messages_are_separate(self):
        spacing = ["단어 사이 공백은 한 칸만 허용합니다."]
        rule = ["닉네임은 한글, 영문, 숫자, 밑줄(_)로 2~12자 입력해 주세요."]
        for value, expected in (("여행  자", spacing), ("여행   자", spacing), ("여행 자!", rule), ("a", rule),
                                ("열세글자를넘는닉네임입니다", rule), ("", None)):
            response = self.client.patch("/api/v1/auth/me/", {"name": value})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, value)
            if expected:
                self.assertEqual(response.data["name"], expected, value)

    def test_change_nickname_rejects_blank_and_bad_format(self):
        for bad in ("", "   ", "a", "여행  자", "열세글자를넘는닉네임입니다", "닉네임!"):
            response = self.client.patch("/api/v1/auth/me/", {"name": bad})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.assertEqual(Profile.objects.get(user=self.user).nickname, "여행자")

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
        self.assertIn("안녕하세요. 여행자님.", mail.outbox[0].body)
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

    def test_password_updated_at_defaults_to_join_date(self):
        data = self.client.get("/api/v1/auth/me/").data
        self.assertEqual(data["password_updated_at"], timezone.localdate(self.user.date_joined).isoformat())

    def test_change_password(self):
        url = "/api/v1/auth/me/password/"
        new = "newroute@2026"
        payload = {"current_password": PASSWORD, "password": new, "password_confirm": new}
        self.assertEqual(self.client.post(url, {**payload, "current_password": "wrong"}).status_code,
                         status.HTTP_400_BAD_REQUEST)
        # 가입 규칙(영문·숫자·특수문자 8~20자), 확인 불일치, 현재와 같은 비밀번호는 거절한다.
        for bad in ({"password": "short1!", "password_confirm": "short1!"},
                    {"password": new, "password_confirm": "different@2026"},
                    {"password": PASSWORD, "password_confirm": PASSWORD}):
            self.assertEqual(self.client.post(url, {**payload, **bad}).status_code, status.HTTP_400_BAD_REQUEST, bad)

        Profile.objects.filter(user=self.user).update(password_changed_at=None)
        Token.objects.create(user=self.user)
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # 모든 로그인이 해제되고, 변경 일자가 오늘로 바뀐다.
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["password_updated_at"],
                         timezone.localdate().isoformat())
        self.client.force_authenticate(None)
        login = self.client.post("/api/v1/auth/login/", {"email": "traveler@example.com", "password": new})
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_social_account_cannot_change_password(self):
        social_user = User.objects.create_user(username="kakao_2", email="")
        social_user.set_unusable_password()
        social_user.save()
        self.client.force_authenticate(social_user)
        self.assertIsNone(self.client.get("/api/v1/auth/me/").data["password_updated_at"])
        response = self.client.post("/api/v1/auth/me/password/",
                                    {"current_password": "x", "password": "a1!bcdefg", "password_confirm": "a1!bcdefg"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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


@override_settings(DEBUG=True)
class SocialLinkTests(APITestCase):
    """마이페이지 계정 연동: 카카오·네이버 연결 / 연결 해제"""

    url = "/api/v1/auth/me/social/kakao/"
    payload = {"code": "auth-code", "redirect_uri": "http://localhost:8002/auth/kakao/callback"}

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="traveler@example.com", email="traveler@example.com", password=PASSWORD
        )
        self.client.force_authenticate(self.user)

    def link(self, uid="kakao-1"):
        profile = SocialProfile(uid=uid, email="", email_verified=False, name="카카오")
        with mock.patch("accounts.social.kakao_profile", return_value=profile):
            return self.client.post(self.url, self.payload, format="json")

    def test_link_then_login_with_kakao(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").data["social_providers"], [])
        response = self.link()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["social_providers"], ["kakao"])
        # 연결한 카카오 계정으로 로그인하면 지금 계정으로 들어온다.
        self.client.force_authenticate(None)
        profile = SocialProfile(uid="kakao-1", email="", email_verified=False, name="카카오")
        with mock.patch("accounts.social.kakao_profile", return_value=profile):
            login = self.client.post("/api/v1/auth/kakao/", self.payload, format="json")
        self.assertEqual(login.data["user"]["id"], self.user.id)

    def test_concurrent_link_to_other_user_is_a_409_not_a_db_error(self):
        # 연결 여부를 확인한 뒤 다른 회원이 같은 카카오 계정을 먼저 연결한 상황
        other = User.objects.create_user(username="kakao_kakao-1")
        SocialAccount.objects.create(user=other, provider="kakao", uid="kakao-1")
        with mock.patch.object(SocialAccount.objects, "filter", return_value=SocialAccount.objects.none()):
            response = self.link()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data, {"detail": "이미 다른 PinRoute 계정에 연결된 카카오 계정이에요."})
        self.assertFalse(self.user.social_accounts.exists())

    def test_cannot_link_account_of_other_user(self):
        other = User.objects.create_user(username="kakao_kakao-1")
        SocialAccount.objects.create(user=other, provider="kakao", uid="kakao-1")
        self.assertEqual(self.link().status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(self.user.social_accounts.exists())

    def test_cannot_link_same_provider_twice(self):
        self.link("kakao-1")
        self.assertEqual(self.link("kakao-2").status_code, status.HTTP_409_CONFLICT)

    def test_unlink(self):
        self.link()
        response = self.client.delete(self.url)
        self.assertEqual(response.data["social_providers"], [])
        self.assertFalse(SocialAccount.objects.exists())

    def test_cannot_unlink_last_login_method(self):
        social_user = User.objects.create_user(username="kakao_kakao-9")
        social_user.set_unusable_password()
        social_user.save()
        SocialAccount.objects.create(user=social_user, provider="kakao", uid="kakao-9")
        self.client.force_authenticate(social_user)
        self.assertEqual(self.client.delete(self.url).status_code, status.HTTP_400_BAD_REQUEST)
        # 네이버도 연결되어 있으면 카카오는 해제할 수 있다.
        SocialAccount.objects.create(user=social_user, provider="naver", uid="naver-9")
        self.assertEqual(self.client.delete(self.url).data["social_providers"], ["naver"])

    def test_unknown_provider(self):
        self.assertEqual(self.client.post("/api/v1/auth/me/social/google/", {}).status_code,
                         status.HTTP_404_NOT_FOUND)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class WithdrawTests(APITestCase):
    """회원 탈퇴: 만든 여행과 회원 정보를 지우고, 다른 사람의 여행에서는 빠지기만 한다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="traveler@example.com", email="traveler@example.com", password=PASSWORD
        )
        Profile.objects.create(user=self.user, phone=PHONE)
        SocialAccount.objects.create(user=self.user, provider="kakao", uid="kakao-1")
        self.token = Token.objects.create(user=self.user)
        self.other = User.objects.create_user(username="other@example.com", email="other@example.com")

    def test_withdraw_deletes_own_data(self):
        own = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                  start_date="2026-11-10", end_date="2026-11-12")
        PackingItem.objects.create(trip=own, text="여권")
        shared = Trip.objects.create(owner=self.other, destinations=[{"city": "오사카", "city_code": "osaka"}],
                                     start_date="2026-12-01", end_date="2026-12-03")
        TripMember.objects.create(trip=shared, user=self.user)

        self.client.force_authenticate(self.user)
        self.client.post("/api/v1/auth/me/avatar/", {"avatar": image_upload()}, format="multipart")
        avatar = Profile.objects.get(user=self.user).avatar
        self.assertTrue(avatar.storage.exists(avatar.name))

        response = self.client.delete("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Trip.objects.filter(pk=own.pk).exists())
        self.assertFalse(PackingItem.objects.exists())
        self.assertFalse(SocialAccount.objects.exists())
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())
        self.assertFalse(avatar.storage.exists(avatar.name))
        # 일행으로 참여한 여행은 남고 일행 목록에서만 빠진다.
        self.assertTrue(Trip.objects.filter(pk=shared.pk).exists())
        self.assertFalse(shared.members.exists())

        # 탈퇴한 계정으로는 로그인할 수 없다.
        self.client.force_authenticate(None)
        login = self.client.post("/api/v1/auth/login/", {"email": "traveler@example.com", "password": PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_400_BAD_REQUEST)

    def test_withdraw_requires_login(self):
        self.assertEqual(self.client.delete("/api/v1/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)


class NicknameGeneratorTests(APITestCase):
    def test_every_combination_follows_nickname_rule(self):
        for adjective in ADJECTIVES:
            for animal in ANIMALS:
                self.assertRegex(f"{adjective} {animal}", NICKNAME_PATTERN)
        self.assertTrue(NICKNAME_PATTERN.match(random_nickname()))

    def test_user_without_nickname_gets_one_once(self):
        user = User.objects.create_user(username="old@example.com", email="old@example.com")
        first = nickname_of(user)
        self.assertEqual(nickname_of(user), first)
        self.assertEqual(Profile.objects.get(user=user).nickname, first)


class NicknameMigrationTests(APITestCase):
    """0006_fill_nicknames: 기존 회원에게 닉네임을 채운다."""

    def test_existing_users_get_nicknames(self):
        import importlib

        from django.apps import apps

        migration = importlib.import_module("accounts.migrations.0006_fill_nicknames")
        keep = User.objects.create_user(username="a@example.com", email="a@example.com", first_name="옛닉네임")
        Profile.objects.create(user=keep)
        odd = User.objects.create_user(username="b@example.com", email="b@example.com", first_name="홍 길동 Hong")
        none = User.objects.create_user(username="c@example.com", email="c@example.com")  # Profile도 없음
        done = User.objects.create_user(username="d@example.com", email="d@example.com", first_name="다른이름")
        Profile.objects.create(user=done, nickname="이미있음")

        migration.fill_nicknames(apps, None)

        self.assertEqual(Profile.objects.get(user=keep).nickname, "옛닉네임")
        self.assertEqual(Profile.objects.get(user=done).nickname, "이미있음")
        for user in (odd, none):
            self.assertRegex(Profile.objects.get(user=user).nickname, NICKNAME_PATTERN)
