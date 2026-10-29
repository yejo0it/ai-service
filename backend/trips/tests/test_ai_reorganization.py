"""재구성용 위치 컨텍스트와 기존 제안→적용 흐름의 회귀 테스트. 외부 API는 모킹한다."""

import os
from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from .. import ai_planner
from ..itinerary_views import days_map
from ..models import Hotel, ItineraryItem, Trip

User = get_user_model()


class CoordinateTests(SimpleTestCase):
    def test_only_valid_rounded_coordinates_are_sent(self):
        self.assertEqual(ai_planner._coordinates(35.714812, 139.796734), "(35.715,139.797)")
        self.assertEqual(ai_planner._coordinates(0, 0), "(0.000,0.000)")
        for point in [(None, 139), (35, None), ("35", 139), (True, 139),
                      (float("nan"), 139), (35, float("inf")), (91, 139), (35, -181), (10 ** 1000, 139)]:
            with self.subTest(point=point):
                self.assertIsNone(ai_planner._coordinates(*point))


class ReorganizationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="reorganize@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(
            owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
            start_date=date(2026, 11, 10), end_date=date(2026, 11, 13), itinerary_initialized=True,
        )
        self.hotel = Hotel.objects.create(
            trip=self.trip, name="숙소", address="보내지 않을 주소", phone="03-1111-2222",
            latitude=35.686211, longitude=139.693211, check_in=self.trip.start_date, check_out=self.trip.end_date,
        )
        self.flight = self.item("가는 편", 0, "flight", "09:00", (35.772, 140.393), "출국")
        self.fixed = self.item("예약한 관광지", 1, "sight", "10:00", (35.7148, 139.7967))
        self.east = self.item("동쪽 장소", 2, "sight", "", (35.7101, 139.8107))
        self.west = self.item("서쪽 장소", 1, "cafe", "", (35.6595, 139.7005))
        self.stay = self.item("체크인", 0, "hotel", "15:00", (35.6862, 139.6932), "체크인")

    def tearDown(self):
        cache.clear()

    def item(self, title, day_index, kind, time, point, time_label=""):
        return ItineraryItem.objects.create(
            trip=self.trip, day=date(2026, 11, 10 + day_index), order=self.trip.itinerary_items.count(),
            title=title, kind=kind, time=time or None, time_label=time_label, stay_minutes=60,
            stops=[{"lat": point[0], "lng": point[1], "label": "비공개 위치 설명"}],
            address="비공개 주소", phone="03-3333-4444",
        )

    def context(self, draft=None):
        days = days_map(self.trip)
        return ai_planner.trip_context(self.trip, sorted(days), days, draft)

    def test_context_links_kind_coordinates_and_stay_to_exact_id(self):
        context = self.context()
        self.assertIn(f"#{self.east.id} 동쪽 장소 [sight;(35.710,139.811);60m]", context)
        self.assertIn(f"#{self.fixed.id} 예약한 관광지 10:00 [sight;(35.715,139.797);60m]", context)
        self.assertIn(f"[hotel_id={self.hotel.id}] 숙소 (2026-11-10~2026-11-13) [(35.686,139.693)]", context)
        self.assertIn("[flight;(35.772,140.393);60m]", context)
        self.assertIn("day_index=1 (2일차, 2026-11-11)", context)
        self.assertIn("day_index=3 (4일차, 2026-11-13)", context)
        for private in ["비공개 위치 설명", "비공개 주소", "보내지 않을 주소", "03-3333-4444", "reorganize@example.com"]:
            self.assertNotIn(private, context)

    def test_missing_coordinates_are_not_guessed_from_title_or_address(self):
        self.east.stops = []
        self.east.save(update_fields=["stops"])
        self.assertIn(f"#{self.east.id} 동쪽 장소 [sight;미상;60m]", self.context())

    def test_multiple_flight_stops_keep_departure_and_arrival(self):
        self.flight.stops = [{"lat": 37.449, "lng": 126.45}, {"lat": 35.772, "lng": 140.393}]
        self.flight.save(update_fields=["stops"])
        self.assertIn("[flight;(37.449,126.450)→(35.772,140.393);60m]", self.context())

    def test_pending_hotels_replace_registered_hotel_coordinates(self):
        context = self.context({"hotels": [{
            "id": None, "name": "새 숙소", "check_in": self.trip.start_date, "check_out": self.trip.end_date,
            "latitude": 34.667, "longitude": 135.502, "address": "비공개 주소",
        }]})
        self.assertIn("[새 숙소] 새 숙소 (2026-11-10~2026-11-13) [(34.667,135.502)]", context)
        self.assertNotIn(f"[hotel_id={self.hotel.id}]", context)
        self.assertNotIn("비공개 주소", context)

    def test_latest_coordinates_are_read_on_each_request(self):
        sent = []

        def parse(**kwargs):
            sent.append(kwargs["messages"][-1]["content"])
            return SimpleNamespace(parsed_output=self.plan(), stop_reason="end_turn", usage=None)

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}), \
                mock.patch("trips.ai_planner.anthropic.Anthropic", return_value=SimpleNamespace(messages=SimpleNamespace(parse=parse))), \
                mock.patch("trips.itinerary_views.guide_search.search_for_trip", return_value=[]):
            self.propose()
            self.east.stops = [{"lat": 34.667, "lng": 135.502}]
            self.east.save(update_fields=["stops"])
            self.propose()
        self.assertIn(f"#{self.east.id} 동쪽 장소 [sight;(35.710,139.811)", sent[0])
        self.assertIn(f"#{self.east.id} 동쪽 장소 [sight;(34.667,135.502)", sent[1])
        self.assertNotIn(f"#{self.east.id} 동쪽 장소 [sight;(35.710,139.811)", sent[1])

    @staticmethod
    def plan(moves=()):
        return ai_planner.PlanResponse(
            reply="지역별로 묶는 제안이에요.", additions=[], remove_item_ids=[], moves=list(moves),
            flight=None, hotel_change=None, form=None, confirm=None, off_topic=False,
        )

    def propose(self):
        return self.client.post(f"/api/v1/trips/{self.trip.id}/ai/propose/", {
            "messages": [{"role": "user", "content": "전체 여행 경로를 가까운 지역끼리 다시 짜줘"}],
        }, format="json")

    def snapshot(self):
        return list(self.trip.itinerary_items.values("id", "day", "order", "time", "kind", "stops"))

    def test_repeated_preview_does_not_write_and_apply_preserves_places_and_fixed_items(self):
        plan = self.plan([
            ai_planner.PlanMove(item_id=self.east.id, day_index=1, time=None),
            ai_planner.PlanMove(item_id=self.west.id, day_index=2, time=None),
        ])
        before = self.snapshot()
        with mock.patch("trips.ai_planner.propose", return_value=plan), \
                mock.patch("trips.itinerary_views.guide_search.search_for_trip", return_value=[]), \
                mock.patch("trips.routes.enabled", return_value=False):
            results = [self.propose() for _ in range(3)]
        self.assertTrue(all(response.status_code == 200 for response in results))
        self.assertEqual(results[0].data["proposal"], results[1].data["proposal"])
        self.assertEqual(results[1].data["preview"], results[2].data["preview"])
        self.assertEqual(before, self.snapshot())
        response = self.client.post(f"/api/v1/trips/{self.trip.id}/ai/apply/", {
            "proposal": results[0].data["proposal"],
        }, format="json")
        self.assertEqual(response.status_code, 200)
        after = self.snapshot()
        self.assertEqual({row["id"] for row in before}, {row["id"] for row in after})
        for fixed in [self.flight, self.fixed, self.stay]:
            old = next(row for row in before if row["id"] == fixed.id)
            new = next(row for row in after if row["id"] == fixed.id)
            self.assertEqual((old["day"], old["time"], old["stops"]), (new["day"], new["time"], new["stops"]))
        actual = {row["id"]: row["day"].isoformat() for row in after}
        preview = {item["id"]: str(day["day"]) for day in results[0].data["preview"] for item in day["items"]}
        self.assertEqual(actual, preview)

    def test_no_change_proposal_keeps_schedule(self):
        before = self.snapshot()
        with mock.patch("trips.ai_planner.propose", return_value=self.plan()), \
                mock.patch("trips.itinerary_views.guide_search.search_for_trip", return_value=[]):
            result = self.propose()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["proposal"]["moves"], [])
        self.assertEqual(before, self.snapshot())
