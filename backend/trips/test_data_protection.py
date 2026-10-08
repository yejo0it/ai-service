"""
AI 데이터 접근 및 유출 방지 (Issue #25)

- 모델에는 로그인한 사용자의 여행 하나에 대한 최소 정보만 보낸다(회원 정보·주소·메모·다른 사용자 데이터 없음).
- 사용자가 채팅에 적은 민감정보는 가리고 보낸다.
- 대화는 서버에 저장되지 않는다.
"""

from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from . import ai_planner, chat_guard
from .itinerary_views import days_map
from .models import ChecklistItem, Hotel, ItineraryItem, Trip

User = get_user_model()


def plan():
    return ai_planner.PlanResponse(reply="정리했어요.", additions=[], remove_item_ids=[], moves=[], form=None,
                                   confirm=None, flight=None, hotel_change=None, off_topic=False)


class RedactTests(APITestCase):
    def test_sensitive_values_are_masked(self):
        cases = {
            "비밀번호는 Hunter2!! 이야": ("비밀번호는 [가림] 이야", "비밀번호"),
            "password: qwer1234": ("password: [가림]", "비밀번호"),
            "내 키 sk-ant-api03-abcdefghijklmnopqrstuvwx 써": ("내 키 [인증 정보] 써", "인증 정보"),
            "Authorization Bearer abcdefghijklmnopqrstu.vwxyz": ("Authorization [인증 정보]", "인증 정보"),
            "주민번호 900101-1234567": ("주민번호 [주민등록번호]", "주민등록번호"),
            "카드 4111 1111 1111 1111로 결제": ("카드 [카드번호]로 결제", "카드번호"),
            "여권 M12345678 챙겨": ("여권 [여권번호] 챙겨", "여권번호"),
            "메일 me.trip@example.com 으로": ("메일 [이메일] 으로", "이메일"),
            "메일은 me@example.com으로 보내줘": ("메일은 [이메일]으로 보내줘", "이메일"),
            "여권번호M12345678을 확인": ("여권번호[여권번호]을 확인", "여권번호"),
            "키는sk-ant-api03-abcdefghijklmnopqrst야": ("키는[인증 정보]야", "인증 정보"),
            "연락처 010-1234-5678": ("연락처 [전화번호]", "전화번호"),
        }
        for text, (expected, label) in cases.items():
            with self.subTest(text=text):
                masked, found = chat_guard.redact_sensitive(text)
                self.assertEqual(masked, expected)
                self.assertIn(label, found)

    def test_travel_text_is_untouched(self):
        texts = [
            "2026-11-10에 인천에서 나리타로 가는 KE703 타고 19:00에 도쿄타워",
            "숙소 전화 03-3343-3111, 체크인 15:00",
            "1박 2일, 예산 150,000엔, 오전 9시 도착",
            "신주쿠 워싱턴 호텔 2박, 하네다 공항 2터미널",
            "예약번호 20261110 확인했어",
        ]
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(chat_guard.redact_sensitive(text), (text, []))


class AiDataScopeTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="private@example.com", email="private@example.com",
                                             first_name="홍길동")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True)
        Hotel.objects.create(trip=self.trip, name="신주쿠 호텔", address="도쿄 신주쿠구 비밀주소 1-2-3",
                             phone="03-1111-2222", check_in="2026-11-10", check_out="2026-11-12")
        item = ItineraryItem.objects.create(trip=self.trip, day="2026-11-10", order=0, kind="sight", source="manual",
                                            title="도쿄타워", address="미나토구 숨은주소", phone="03-3333-4444",
                                            memo="개인 메모: 카드 비번 적어둠", stops=[])
        ChecklistItem.objects.create(item=item, text="여권 사본 챙기기")
        other = User.objects.create_user(username="someone@example.com", email="someone@example.com")
        other_trip = Trip.objects.create(owner=other, destinations=[{"city": "오사카", "city_code": "osaka"}],
                                         start_date="2026-11-10", end_date="2026-11-12")
        ItineraryItem.objects.create(trip=other_trip, day="2026-11-10", order=0, kind="sight", source="manual",
                                     title="남의 비밀 일정", stops=[])

    def tearDown(self):
        cache.clear()

    def test_context_has_only_minimum_trip_data(self):
        self.trip.refresh_from_db()
        days = days_map(self.trip)
        context = ai_planner.trip_context(self.trip, sorted(days), days)
        for expected in ("도쿄", "2026-11-10", "신주쿠 호텔", "도쿄타워"):
            self.assertIn(expected, context)
        for hidden in ("private@example.com", "홍길동", "비밀주소", "숨은주소", "03-1111-2222", "03-3333-4444",
                       "개인 메모", "여권 사본", "남의 비밀 일정", "오사카", "someone@example.com"):
            self.assertNotIn(hidden, context)

    def test_chat_is_masked_and_not_stored(self):
        counts = {model.__name__: model.objects.count() for model in apps.get_models()}
        with mock.patch("trips.ai_planner.propose", return_value=plan()) as propose:
            response = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/", {"messages": [
                {"role": "user", "content": "카드 4111-1111-1111-1111 이고 비밀번호 abc123 이야. 맛집 추천해줘"},
                {"role": "assistant", "content": "좋아요."},
                {"role": "user", "content": "메일은 me@example.com 이야"},
            ]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sent = " ".join(turn["content"] for turn in propose.call_args.args[3])
        for secret in ("4111-1111-1111-1111", "abc123", "me@example.com"):
            self.assertNotIn(secret, sent)
        self.assertIn("맛집 추천해줘", sent)
        self.assertEqual(sorted(response.data["redacted"]), ["비밀번호", "이메일", "카드번호"])
        # 대화를 저장하는 곳이 없다: 제안 요청 전후로 DB 데이터가 그대로다.
        self.assertEqual(counts, {model.__name__: model.objects.count() for model in apps.get_models()})
