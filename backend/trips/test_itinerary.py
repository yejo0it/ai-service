import os
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from . import ai_planner
from .models import ChecklistItem, Hotel, ItineraryItem, Trip

User = get_user_model()

NRT = {"lat": 35.772, "lng": 140.3929}
SHINJUKU = (35.6862, 139.6932)
SHIBUYA = (35.6595, 139.7005)       # 신주쿠 숙소와 가까움
ASAKUSA = (35.7148, 139.7967)       # 스카이트리 쪽
SKYTREE = (35.7101, 139.8107)
OSAKA_HOTEL = (34.6667, 135.5023)
DOTONBORI = (34.6687, 135.5013)


def detail(name, point, place_id="pid"):
    return {
        "place_id": place_id, "name": name, "address": f"{name} 주소",
        "latitude": point[0], "longitude": point[1], "phone": "03-0000-0000",
        "opening_hours": ["월요일: 10:00~22:00"],
    }


class ItineraryTests(APITestCase):
    """일정 저장·직접 추가 배치·순서·체크리스트·짐싸기 노트"""

    def setUp(self):
        self.user = User.objects.create_user(username="me@example.com", email="me@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(
            owner=self.user,
            destinations=[{"city": "도쿄", "city_code": "TYO"}, {"city": "오사카", "city_code": "OSA"}],
            start_date="2026-10-12",
            end_date="2026-10-15",
        )
        Hotel.objects.create(trip=self.trip, name="신주쿠 호텔", address="신주쿠", latitude=SHINJUKU[0],
                             longitude=SHINJUKU[1], check_in="2026-10-12", check_out="2026-10-14")
        Hotel.objects.create(trip=self.trip, name="난바 호텔", address="난바", latitude=OSAKA_HOTEL[0],
                             longitude=OSAKA_HOTEL[1], check_in="2026-10-14", check_out="2026-10-15")
        hotel_stop = {"kind": "hotel", "caption": "체크인", "label": "신주쿠", "lat": SHINJUKU[0], "lng": SHINJUKU[1]}
        self.init_items = [
            {"day": "2026-10-12", "kind": "flight", "title": "가는 편", "time": "09:00", "time_label": "출국",
             "stops": [{"kind": "airport", "caption": "출발", "label": "인천", "lat": 37.449, "lng": 126.45},
                       {"kind": "airport", "caption": "도착", "label": "나리타", **NRT}]},
            {"day": "2026-10-12", "kind": "hotel", "title": "신주쿠 호텔", "time_label": "체크인", "stops": [hotel_stop]},
            {"day": "2026-10-13", "kind": "hotel", "title": "신주쿠 호텔", "time_label": "숙박", "stops": [hotel_stop]},
        ]

    def url(self, suffix=""):
        return f"/api/v1/trips/{self.trip.pk}/itinerary/{suffix}"

    def titles(self, day):
        return list(self.trip.itinerary_items.filter(day=day).values_list("title", flat=True))

    def init(self):
        return self.client.post(self.url("init/"), {"items": self.init_items}, format="json")

    def add(self, name, point, day, time=""):
        with mock.patch("trips.places.place_details", return_value=detail(name, point)):
            return self.client.post(
                self.url(), {"kind": "sight", "day": day, "time": time, "place_id": "pid"}, format="json"
            )

    def test_init_saves_once(self):
        response = self.init()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["initialized"])
        self.assertEqual(len(response.data["items"]), 3)
        self.init()
        self.assertEqual(self.trip.itinerary_items.count(), 3)

    def test_added_place_goes_between_fixed_cards(self):
        self.init()
        response = self.add("도쿄타워", (35.6586, 139.7454), "2026-10-12")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 출국편(시작 고정) 뒤, 체크인(끝 고정) 앞
        self.assertEqual(self.titles("2026-10-12"), ["가는 편", "도쿄타워", "신주쿠 호텔"])
        item = self.trip.itinerary_items.get(title="도쿄타워")
        self.assertEqual((item.source, item.phone, item.stops[0]["kind"]), ("manual", "03-0000-0000", "place"))

    def test_untimed_place_goes_where_detour_is_smallest(self):
        self.init()
        self.add("아사쿠사", ASAKUSA, "2026-10-13")
        self.add("시부야", SHIBUYA, "2026-10-13")
        # 스카이트리는 시부야보다 아사쿠사 바로 옆에 두는 것이 덜 돌아간다.
        self.add("스카이트리", SKYTREE, "2026-10-13")
        titles = self.titles("2026-10-13")
        self.assertEqual(abs(titles.index("스카이트리") - titles.index("아사쿠사")), 1)

    def test_timed_place_follows_time_order(self):
        self.init()
        self.add("점심", SHIBUYA, "2026-10-13", "12:00")
        self.add("저녁", ASAKUSA, "2026-10-13", "19:00")
        self.add("아침", SKYTREE, "2026-10-13", "08:00")
        self.assertEqual(self.titles("2026-10-13"), ["신주쿠 호텔", "아침", "점심", "저녁"])

    def test_reorder_and_mismatch(self):
        self.init()
        self.add("A", SHIBUYA, "2026-10-13")
        ids = list(self.trip.itinerary_items.filter(day="2026-10-13").values_list("id", flat=True))
        response = self.client.post(self.url("reorder/"), {"day": "2026-10-13", "ids": ids[::-1]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.titles("2026-10-13"), ["A", "신주쿠 호텔"])
        response = self.client.post(self.url("reorder/"), {"day": "2026-10-13", "ids": ids[:1]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_checklist_classification_and_packing_note(self):
        self.init()
        self.add("스카이트리", SKYTREE, "2026-10-13")
        item = self.trip.itinerary_items.get(title="스카이트리")
        url = f"/api/v1/itinerary-items/{item.pk}/checklist/"
        ticket = self.client.post(url, {"text": "웹으로 티켓 사전 예매"}, format="json").data
        photo = self.client.post(url, {"text": "전망대에서 사진 찍기"}, format="json").data
        self.assertTrue(ticket["in_packing_note"])
        self.assertFalse(photo["in_packing_note"])

        self.client.patch(f"/api/v1/checklist-items/{photo['id']}/", {"in_packing_note": True}, format="json")
        self.client.patch(f"/api/v1/checklist-items/{ticket['id']}/", {"done": True}, format="json")
        linked = self.client.get(f"/api/v1/trips/{self.trip.pk}/packing-note/").data["linked"]
        self.assertEqual([(c["text"], c["done"], c["item_title"]) for c in linked], [
            ("웹으로 티켓 사전 예매", True, "스카이트리"),
            ("전망대에서 사진 찍기", False, "스카이트리"),
        ])

    def test_memo_and_delete_only_own_items(self):
        self.init()
        item = self.trip.itinerary_items.first()
        response = self.client.patch(f"/api/v1/itinerary-items/{item.pk}/", {"memo": "전화 예약 필수"}, format="json")
        self.assertEqual(response.data["memo"], "전화 예약 필수")
        other = User.objects.create_user(username="other@example.com")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.delete(f"/api/v1/itinerary-items/{item.pk}/").status_code, 404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(f"/api/v1/itinerary-items/{item.pk}/").status_code, 204)


class AiPlanTests(ItineraryTests):
    """AI와 함께 만들기: 제안 미리보기와 적용 (모델·장소 검색은 모킹)"""

    def plan(self):
        return ai_planner.PlanResponse(
            reply="스카이트리와 도톤보리를 넣었어요.",
            additions=[
                ai_planner.PlanAddition(name="스카이트리", search_query="도쿄 스카이트리", kind="sight",
                                        day_index=None, time=None, reason="전망", checklist=["웹으로 티켓 사전 예매"]),
                ai_planner.PlanAddition(name="도톤보리", search_query="도톤보리 오사카", kind="sight",
                                        day_index=None, time=None, reason="야경", checklist=[]),
                ai_planner.PlanAddition(name="없는 곳", search_query="없는 곳", kind="cafe",
                                        day_index=0, time=None, reason="", checklist=[]),
            ],
            remove_item_ids=[],
            moves=[],
        )

    def search(self, text, *args):
        return {"도쿄 스카이트리": detail("스카이트리", SKYTREE, "a"), "도톤보리 오사카": detail("도톤보리", DOTONBORI, "b")}.get(text)

    def test_propose_then_apply(self):
        self.init()
        with mock.patch("trips.ai_planner.propose", return_value=self.plan()), \
                mock.patch("trips.places.search_place", side_effect=self.search):
            response = self.client.post(
                f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                {"messages": [{"role": "user", "content": "스카이트리랑 도톤보리 가고 싶어"}]},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["unresolved"], ["없는 곳"])
        new_by_day = {
            str(day["day"]): [i["title"] for i in day["items"] if i["status"] == "new"] for day in response.data["preview"]
        }
        # 날짜를 정하지 않아도 숙소가 가까운 날로: 스카이트리는 신주쿠 숙박일, 도톤보리는 난바 숙박일
        self.assertIn("스카이트리", new_by_day["2026-10-12"] + new_by_day["2026-10-13"])
        self.assertEqual(new_by_day["2026-10-14"], ["도톤보리"])
        self.assertEqual(self.trip.itinerary_items.count(), 3)  # 미리보기는 저장하지 않는다

        response = self.client.post(
            f"/api/v1/trips/{self.trip.pk}/ai/apply/", {"proposal": response.data["proposal"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skytree = ItineraryItem.objects.get(trip=self.trip, title="스카이트리")
        self.assertEqual(skytree.source, "ai")
        self.assertTrue(ChecklistItem.objects.get(item=skytree).in_packing_note)
        self.assertEqual(self.titles("2026-10-14"), ["도톤보리"])

    def test_propose_without_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            response = self.client.post(
                f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                {"messages": [{"role": "user", "content": "추천해 줘"}]},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
