"""
예외가 만들어지는 지점에서 민감정보가 로그·응답에 남지 않게 처리한다 (Issue #95).

- AI 응답 검증 실패(pydantic ValidationError): 오류 메시지에 모델 출력 일부(여행·예약 내용)가 들어 있으므로 고정 문구 오류로
  바꾸고 원래 예외를 이어 붙이지 않는다.
- 숙소 목록 ?trip=: 숫자가 아니면 500(입력값이 traceback에 남음) 대신 400.
- 장소 사진 실패 로그·fill_hotel_phones 출력: 예외 메시지·사용자가 등록한 숙소 이름 대신 종류·상태 코드·id만.
"""

import io
import json
import os
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from pydantic import TypeAdapter, ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from . import ai_planner, ai_usage, place_photos, places
from .models import Hotel, Trip
from .reservations import extract, files
from .reservations.schemas import HotelDocument

User = get_user_model()

FAKE_TRIP_TEXT = "FAKEPLACE-가짜장소 첫째 날 FAKEHOTEL-가짜호텔 근처 "
FAKE_STAY_TEXT = '{"stays":[{"name":"FAKEHOTEL Shinjuku","address":"FAKEADDR 1-2-3 Tokyo'


def truncated_output_error(model, text):
    """max_tokens에서 잘린 응답을 SDK가 검증할 때와 같은 실제 pydantic ValidationError"""
    try:
        TypeAdapter(model).validate_json(text)
    except ValidationError as exc:
        return exc
    raise AssertionError("검증이 실패해야 한다")


class FailingMessages:
    def __init__(self, error):
        self.error = error

    def parse(self, **kwargs):
        raise self.error


class PlannerValidationErrorTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="err@example.com", email="err@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True)

    def tearDown(self):
        cache.clear()

    def test_truncated_model_output_becomes_a_fixed_error_without_the_output(self):
        error = truncated_output_error(ai_planner.PlanResponse, '{"reply":"' + FAKE_TRIP_TEXT * 6)
        self.assertIn("FAKEPLACE", str(error))  # 원래 예외 메시지에는 모델 출력이 들어 있다
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-TEST-ERR"}), \
                mock.patch("trips.ai_planner.anthropic.Anthropic",
                           return_value=SimpleNamespace(messages=FailingMessages(error))), \
                mock.patch("guides.search.search_for_trip", return_value=[]), \
                self.assertLogs(ai_usage.LOGGER_NAME, "INFO") as logs:
            response = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                        {"messages": [{"role": "user", "content": "일정 다시 짜줘"}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data, {"detail": "AI 응답을 이해하지 못했어요. 다시 시도해 주세요."})
        records = [json.loads(line.split(":", 2)[2]) for line in logs.output]
        self.assertEqual([(r["event"], r.get("error"), r.get("outcome")) for r in records],
                         [("claude_call", "ValidationError", None), ("ai_request", None, "planner_error")])
        self.assertNotIn("FAKEPLACE", "\n".join(logs.output))

    def test_planner_error_does_not_chain_the_validation_error(self):
        error = truncated_output_error(ai_planner.PlanResponse, '{"reply":"' + FAKE_TRIP_TEXT)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-TEST-ERR"}), \
                mock.patch("trips.ai_planner.anthropic.Anthropic",
                           return_value=SimpleNamespace(messages=FailingMessages(error))), \
                mock.patch("trips.ai_planner.trip_context", return_value=""), \
                self.assertLogs(ai_usage.LOGGER_NAME, "INFO"):
            with self.assertRaises(ai_planner.PlannerError) as raised:
                ai_planner.propose(self.trip, [], {}, [{"role": "user", "content": "일정 다시 짜줘"}],
                                   source=ai_usage.SOURCE_USER)
        # 나중에 누가 exc_info로 기록해도 모델 출력이 traceback에 이어 붙지 않는다.
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)


class ReservationValidationErrorTests(SimpleTestCase):
    def test_truncated_reservation_output_becomes_a_fixed_error(self):
        error = truncated_output_error(HotelDocument, FAKE_STAY_TEXT)
        self.assertIn("FAKEADDR", str(error))
        client = SimpleNamespace(messages=FailingMessages(error))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-TEST-ERR"}), \
                mock.patch("trips.reservations.extract.anthropic.Anthropic", return_value=client):
            with self.assertRaises(extract.ReservationAiError) as raised:
                extract.extract("hotel", files.PreparedDocument(method=files.PDF_TEXT, pages=1, text="x"))
        self.assertEqual(str(raised.exception), "AI 응답을 이해하지 못했어요. 다시 시도하거나 직접 입력해 주세요.")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)


class HotelTripFilterTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="hotel@example.com", email="hotel@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[], start_date="2026-11-10", end_date="2026-11-12")
        self.hotel = Hotel.objects.create(trip=self.trip, name="가짜 호텔", check_in="2026-11-10", check_out="2026-11-12")

    def test_non_numeric_trip_is_a_400_not_a_500(self):
        for value in ("abcFAKEINPUT", "1;drop", "²", "-1", "1.5"):
            with self.subTest(value=value):
                response = self.client.get("/api/v1/hotels/", {"trip": value})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data, {"trip": ["여행 ID가 올바르지 않습니다."]})

    def test_numeric_trip_still_filters(self):
        response = self.client.get("/api/v1/hotels/", {"trip": str(self.trip.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([h["id"] for h in response.data["results"]], [self.hotel.pk])
        self.assertEqual(self.client.get("/api/v1/hotels/", {"trip": str(self.trip.pk + 999)}).data["results"], [])


class ErrorOutputTests(TestCase):
    def test_place_photo_failure_logs_only_kind_and_status(self):
        with mock.patch("trips.places._request", side_effect=places.PlacesError("FAKE-응답-본문 secret", status_code=503)), \
                self.assertLogs("trips.place_photos", "WARNING") as logs:
            self.assertEqual(place_photos.lookup("ChIJFAKEPLACE")["status"], place_photos.ERROR)
        self.assertEqual(logs.output, ["WARNING:trips.place_photos:place photo failed for ChIJFAKEPLACE: PlacesError(503)"])

    def test_fill_hotel_phones_prints_id_not_name_or_message(self):
        user = User.objects.create_user(username="phones@example.com", email="phones@example.com")
        trip = Trip.objects.create(owner=user, destinations=[], start_date="2026-11-10", end_date="2026-11-12")
        hotel = Hotel.objects.create(trip=trip, name="FAKE 사용자 숙소", place_id="ChIJFAKEHOTEL",
                                     check_in="2026-11-10", check_out="2026-11-12")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("trips.places.place_details", side_effect=places.PlacesError("FAKE-응답-본문")):
            call_command("fill_hotel_phones", stdout=out, stderr=err)
        self.assertEqual(err.getvalue().strip(), f"숙소 #{hotel.pk}: PlacesError(502)")
        self.assertIn("전화번호를 채운 숙소: 0 / 1", out.getvalue())
