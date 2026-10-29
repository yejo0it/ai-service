"""
기존 여행에 예약 확인서 추가(3단계)

- 미리보기는 아무것도 저장하지 않고, 새 예약·이미 있는 예약·숙소 겹침·기간 변경·함께 빠지는 자동 카드·시간이 겹치는 기존 일정을 알려 준다.
- 저장은 한 트랜잭션: 예약 정보를 저장하고 사용자가 승인한 변경만 경로에 반영한다. 같은 예약을 다시 보내면 건너뛴다.
- 사용자가 만든 일정(관광지·식당 등)은 사용자가 지우기로 고른 충돌 일정 말고는 바뀌지 않는다.
- 직접 등록한 항공은 예약 구간으로 교체하고, 구간이 있으면 기본은 추가(전체 교체 선택 가능).
- 숙소가 겹치면 건너뛰기(기본) 또는 기존 숙소 교체. 예약 항공 구간은 하나씩 지울 수 있다.
"""

from datetime import date, time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import FlightSegment, Hotel, ItineraryItem, Trip, TripMember

User = get_user_model()


def segment(number, dep, arr, dep_date, dep_time, arr_date, arr_time, direction=None):
    return {
        "airline_name": "대한항공", "flight_number": number,
        "departure_airport_code": dep, "departure_airport_name": None,
        "arrival_airport_code": arr, "arrival_airport_name": None,
        "departure_date": dep_date, "departure_time": dep_time,
        "arrival_date": arr_date, "arrival_time": arr_time, "direction": direction, "notes": [],
    }


def flight(*segments):
    return {"itineraries": [{"status": None, "segments": list(segments)}]}


ROUND = flight(
    segment("KE703", "ICN", "NRT", "2026-11-10", "09:05", "2026-11-10", "11:20", "outbound"),
    segment("KE704", "NRT", "ICN", "2026-11-14", "18:40", "2026-11-14", "21:15", "return"),
)


def stay(name, check_in, check_out, check_in_time=None):
    return {"name": name, "address": None, "check_in_date": check_in, "check_out_date": check_out,
            "check_in_time": check_in_time, "check_out_time": None, "status": None, "notes": []}


def card(day, title, time_label, kind="flight", time_value=""):
    return {"day": day, "kind": kind, "title": title, "time": time_value, "time_label": time_label, "subtitle": "", "stops": []}


@override_settings(RESERVATION_ANALYSIS_ENABLED=True)
class AddReservationTestBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="u@example.com", email="u@example.com")
        self.client.force_authenticate(self.user)
        for target in ("trips.reservations.extract.anthropic.Anthropic", "trips.places._request", "trips.travel_info._get_json"):
            patcher = mock.patch(target, side_effect=AssertionError(f"{target} 호출 금지"))
            patcher.start()
            self.addCleanup(patcher.stop)
        # 직접 등록한 여행: 가는 편·오는 편(flight_info만), 숙소 하나, 사용자가 만든 일정 둘
        self.trip = Trip.objects.create(
            owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
            start_date=date(2026, 11, 10), end_date=date(2026, 11, 14), itinerary_initialized=True,
            flight_info={"flight_number": "OZ101", "departure_at": "2026-11-10T08:00:00"},
        )
        self.old_flight = ItineraryItem.objects.create(trip=self.trip, day=date(2026, 11, 10), order=0, kind="flight", source="auto",
                                                       title="가는 편 · OZ101", time_label="출국")
        self.hotel = Hotel.objects.create(trip=self.trip, name="신주쿠 호텔", address="", check_in=date(2026, 11, 10), check_out=date(2026, 11, 12))
        self.hotel_cards = [
            ItineraryItem.objects.create(trip=self.trip, day=date(2026, 11, d), order=5, kind="hotel", source="auto",
                                         title="신주쿠 호텔", time_label=label)
            for d, label in ((10, "체크인"), (11, "숙박"), (12, "체크아웃"))
        ]
        # 사용자가 만든 일정: 10일 10:00(비행 시간과 겹침), 11일 13:00(겹치지 않음)
        self.early_sight = ItineraryItem.objects.create(trip=self.trip, day=date(2026, 11, 10), order=1, kind="sight", source="manual",
                                                        title="센소지", time=time(10, 0))
        self.later_meal = ItineraryItem.objects.create(trip=self.trip, day=date(2026, 11, 11), order=1, kind="restaurant", source="manual",
                                                       title="이치란", time=time(13, 0))

    def url(self, action, trip=None):
        return f"/api/v1/trips/{(trip or self.trip).id}/reservations/{action}/"

    def preview(self, **body):
        return self.client.post(self.url("preview"), body, format="json")

    def apply(self, **body):
        return self.client.post(self.url("apply"), body, format="json")

    def titles(self):
        return set(self.trip.itinerary_items.values_list("title", flat=True))


class PreviewTests(AddReservationTestBase):
    def test_preview_saves_nothing(self):
        before = (FlightSegment.objects.count(), Hotel.objects.count(), ItineraryItem.objects.count(), self.trip.flight_info)
        response = self.preview(flight=ROUND)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.trip.refresh_from_db()
        self.assertEqual((FlightSegment.objects.count(), Hotel.objects.count(), ItineraryItem.objects.count(), self.trip.flight_info), before)

    def test_direct_flight_is_replaced_and_old_cards_are_listed(self):
        data = self.preview(flight=ROUND).data
        self.assertEqual((data["flight"]["mode"], data["flight"]["legacy_replaced"], data["flight"]["final_count"]), ("replace", True, 2))
        self.assertEqual([c["id"] for c in data["replaced_cards"]], [self.old_flight.id])
        self.assertEqual(data["dates"]["extend"], False)
        self.assertTrue(data["itinerary_initialized"])

    def test_time_conflicts_list_only_user_items_within_the_flight_window(self):
        conflicts = self.preview(flight=ROUND).data["conflicts"]
        # KE703 09:05~11:20 -> 07:05~12:20: 10일 10:00 센소지만 겹친다(11일 이치란·자동 카드는 아님).
        self.assertEqual([(c["id"], c["title"]) for c in conflicts], [(self.early_sight.id, "센소지")])
        self.assertIn("KE703", conflicts[0]["reason"])

    def test_dates_outside_the_trip_need_extension(self):
        late = flight(segment("KE704", "NRT", "ICN", "2026-11-16", "18:40", "2026-11-16", "21:15"))
        dates = self.preview(flight=late).data["dates"]
        self.assertEqual((dates["extend"], dates["start"], dates["end"]), (True, "2026-11-10", "2026-11-16"))

    def test_hotel_statuses(self):
        hotels = {"stays": [
            stay("신주쿠 호텔", "2026-11-10", "2026-11-12"),  # 이미 있는 예약
            stay("아사쿠사 료칸", "2026-11-11", "2026-11-13"),  # 신주쿠 호텔과 11일 밤이 겹침
            stay("우에노 호텔", "2026-11-13", "2026-11-14"),  # 겹치는 숙소가 없음
        ]}
        data = self.preview(hotels=hotels).data
        self.assertEqual([h["status"] for h in data["hotels"]], ["duplicate", "skip", "new"])
        self.assertEqual([o["name"] for o in data["hotels"][1]["overlaps"]], ["신주쿠 호텔"])
        replaced = self.preview(hotels=hotels, hotel_decisions=["skip", "replace", "skip"]).data
        self.assertEqual(replaced["hotels"][1]["status"], "replace")
        self.assertEqual({c["id"] for c in replaced["replaced_cards"]}, {c.id for c in self.hotel_cards})

    def test_invalid_input(self):
        self.assertEqual(self.preview().status_code, status.HTTP_400_BAD_REQUEST)  # 둘 다 없음
        broken = flight(segment(None, "ICN", "NRT", "2026-11-10", "09:05", None, None))
        response = self.preview(flight=broken)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("flight", response.data)
        overlapping_new = {"stays": [stay("A", "2026-11-12", "2026-11-14"), stay("B", "2026-11-13", "2026-11-14")]}
        self.assertEqual(self.preview(hotels=overlapping_new).status_code, status.HTTP_400_BAD_REQUEST)


class ApplyFlightTests(AddReservationTestBase):
    def test_save_and_reflect_only_approved_changes(self):
        cards = [card("2026-11-10", "가는 편 · KE703", "출국", time_value="09:05"), card("2026-11-14", "오는 편 · KE704", "귀국", time_value="18:40")]
        response = self.apply(flight=ROUND, reflect=True, cards=cards, remove_item_ids=[])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.trip.refresh_from_db()
        self.assertEqual(list(self.trip.flight_segments.values_list("flight_number", flat=True)), ["KE703", "KE704"])
        self.assertEqual(self.trip.flight_info["flight_number"], "KE703")  # 요약도 예약 구간으로
        titles = self.titles()
        self.assertNotIn("가는 편 · OZ101", titles)  # 교체한 항공의 자동 카드는 함께 빠진다.
        self.assertTrue({"가는 편 · KE703", "오는 편 · KE704", "센소지", "이치란", "신주쿠 호텔"} <= titles)  # 사용자 일정은 그대로
        self.assertEqual([s["flight_number"] for s in response.data["trip"]["flight_segments"]], ["KE703", "KE704"])
        self.assertIn("items", response.data)

    def test_conflicting_item_is_removed_only_when_approved(self):
        self.apply(flight=ROUND, reflect=True, cards=[], remove_item_ids=[])
        self.assertTrue(ItineraryItem.objects.filter(pk=self.early_sight.pk).exists())
        self.trip.flight_segments.all().delete()
        self.trip.flight_info = None
        self.trip.save()
        self.apply(flight=ROUND, reflect=True, cards=[], remove_item_ids=[self.early_sight.id, self.later_meal.id])
        self.assertFalse(ItineraryItem.objects.filter(pk=self.early_sight.pk).exists())  # 승인한 충돌 일정
        self.assertTrue(ItineraryItem.objects.filter(pk=self.later_meal.pk).exists())  # 충돌 목록에 없는 일정은 지우지 않는다.

    def test_save_only_does_not_add_cards_or_remove_user_items(self):
        cards = [card("2026-11-10", "가는 편 · KE703", "출국")]
        self.apply(flight=ROUND, reflect=False, cards=cards, remove_item_ids=[self.early_sight.id])
        self.assertEqual(self.trip.flight_segments.count(), 2)
        titles = self.titles()
        self.assertNotIn("가는 편 · KE703", titles)
        self.assertIn("센소지", titles)

    def test_add_mode_appends_and_skips_duplicates(self):
        self.apply(flight=flight(ROUND["itineraries"][0]["segments"][0]), reflect=False)
        again = self.preview(flight=ROUND).data["flight"]
        self.assertEqual((again["mode"], [s["flight_number"] for s in again["new"]], [s["flight_number"] for s in again["duplicates"]]),
                         ("add", ["KE704"], ["KE703"]))
        self.apply(flight=ROUND, reflect=False)
        self.assertEqual(list(self.trip.flight_segments.values_list("order", "flight_number")), [(0, "KE703"), (1, "KE704")])
        self.apply(flight=ROUND, reflect=False)  # 같은 예약을 다시 저장해도 늘지 않는다.
        self.assertEqual(self.trip.flight_segments.count(), 2)

    def test_replace_mode_replaces_all_segments(self):
        self.apply(flight=ROUND, reflect=False)
        other = flight(segment("JL91", "HND", "GMP", "2026-11-14", "10:00", "2026-11-14", "12:30", "return"))
        self.apply(flight=other, flight_mode="replace", reflect=False)
        self.assertEqual(list(self.trip.flight_segments.values_list("flight_number", flat=True)), ["JL91"])

    def test_extension_requires_consent_and_nothing_is_saved_without_it(self):
        late = flight(segment("KE704", "NRT", "ICN", "2026-11-16", "18:40", "2026-11-16", "21:15"))
        response = self.apply(flight=late, reflect=False)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.trip.refresh_from_db()
        self.assertEqual((str(self.trip.end_date), self.trip.flight_segments.count()), ("2026-11-14", 0))
        self.assertEqual(self.trip.flight_info["flight_number"], "OZ101")
        self.assertEqual(self.apply(flight=late, reflect=False, extend_dates=True).status_code, 200)
        self.trip.refresh_from_db()
        self.assertEqual(str(self.trip.end_date), "2026-11-16")

    def test_cards_outside_trip_or_of_other_kinds_are_ignored(self):
        cards = [card("2026-12-01", "가는 편 · KE703", "출국"), card("2026-11-11", "몰래 넣은 관광지", "", kind="sight")]
        self.apply(flight=ROUND, reflect=True, cards=cards)
        self.assertFalse({"몰래 넣은 관광지"} & self.titles())

    def test_uninitialized_itinerary_gets_no_cards(self):
        self.trip.itinerary_initialized = False
        self.trip.save()
        self.apply(flight=ROUND, reflect=True, cards=[card("2026-11-10", "가는 편 · KE703", "출국")])
        self.assertNotIn("가는 편 · KE703", self.titles())  # 상세를 처음 열 때 예약 정보로 만들어진다.


class ApplyHotelTests(AddReservationTestBase):
    def test_new_hotel_with_cards(self):
        hotels = {"stays": [stay("우에노 호텔", "2026-11-12", "2026-11-14", "15:00")]}
        cards = [card("2026-11-12", "우에노 호텔", "체크인", kind="hotel", time_value="15:00"), card("2026-11-14", "우에노 호텔", "체크아웃", kind="hotel")]
        self.apply(hotels=hotels, reflect=True, cards=cards, hotel_places=[{"place_id": "p1", "latitude": 35.7, "longitude": 139.77}])
        hotel = Hotel.objects.get(name="우에노 호텔")
        self.assertEqual((str(hotel.check_in_time), hotel.place_id, hotel.latitude), ("15:00:00", "p1", 35.7))
        self.assertEqual(self.trip.itinerary_items.filter(title="우에노 호텔").count(), 2)

    def test_overlap_skip_by_default_and_replace_when_chosen(self):
        overlapping = {"stays": [stay("아사쿠사 료칸", "2026-11-11", "2026-11-13")]}
        self.apply(hotels=overlapping, reflect=True)
        self.assertFalse(Hotel.objects.filter(name="아사쿠사 료칸").exists())  # 기본은 건너뛰기
        self.assertTrue(Hotel.objects.filter(pk=self.hotel.pk).exists())
        self.apply(hotels=overlapping, hotel_decisions=["replace"], reflect=True,
                   cards=[card("2026-11-11", "아사쿠사 료칸", "체크인", kind="hotel")])
        self.assertFalse(Hotel.objects.filter(pk=self.hotel.pk).exists())
        self.assertFalse(ItineraryItem.objects.filter(pk__in=[c.pk for c in self.hotel_cards]).exists())  # 기존 숙소 카드도 함께
        self.assertTrue(Hotel.objects.filter(name="아사쿠사 료칸").exists())
        self.assertTrue({"센소지", "이치란", "아사쿠사 료칸"} <= self.titles())

    def test_duplicate_hotel_is_skipped(self):
        self.apply(hotels={"stays": [stay("신주쿠 호텔", "2026-11-10", "2026-11-12")]}, reflect=False)
        self.assertEqual(Hotel.objects.filter(name="신주쿠 호텔").count(), 1)

    def test_partial_failure_rolls_back_everything(self):
        hotels = {"stays": [stay("우에노 호텔", "2026-11-12", "2026-11-14")]}
        with mock.patch.object(Hotel.objects, "create", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                self.apply(flight=ROUND, hotels=hotels, reflect=True)
        self.trip.refresh_from_db()
        self.assertEqual((self.trip.flight_segments.count(), self.trip.flight_info["flight_number"]), (0, "OZ101"))
        self.assertTrue(ItineraryItem.objects.filter(pk=self.old_flight.pk).exists())

    def test_invalid_hotel_saves_nothing_even_with_valid_flight(self):
        bad = {"stays": [stay("우에노 호텔", "2026-11-14", "2026-11-12")]}
        self.assertEqual(self.apply(flight=ROUND, hotels=bad, reflect=True).status_code, 400)
        self.assertEqual(self.trip.flight_segments.count(), 0)


class SegmentDeleteTests(AddReservationTestBase):
    def setUp(self):
        super().setUp()
        cards = [card("2026-11-10", "가는 편 · KE703", "출국"), card("2026-11-14", "오는 편 · KE704", "귀국")]
        self.apply(flight=ROUND, reflect=True, cards=cards)

    def delete(self, order, trip=None):
        return self.client.delete(f"/api/v1/trips/{(trip or self.trip).id}/flight-segments/{order}/")

    def test_delete_segment_and_its_card(self):
        response = self.delete(0)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(list(self.trip.flight_segments.values_list("order", "flight_number")), [(0, "KE704")])
        self.assertNotIn("가는 편 · KE703", self.titles())
        self.assertIn("오는 편 · KE704", self.titles())
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.flight_info["flight_number"], "KE704")
        self.assertTrue({"센소지", "이치란"} <= self.titles())

    def test_delete_last_segment_clears_flight(self):
        self.delete(1)
        self.delete(0)
        self.trip.refresh_from_db()
        self.assertEqual((self.trip.flight_info, self.trip.date_source, self.trip.flight_segments.count()), (None, "manual", 0))

    def test_missing_segment(self):
        self.assertEqual(self.delete(9).status_code, status.HTTP_404_NOT_FOUND)


class AccessTests(AddReservationTestBase):
    def test_stranger_cannot_preview_apply_or_delete(self):
        stranger = User.objects.create_user(username="s@example.com", email="s@example.com")
        self.client.force_authenticate(stranger)
        self.assertEqual(self.preview(flight=ROUND).status_code, 404)
        self.assertEqual(self.apply(flight=ROUND).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/trips/{self.trip.id}/flight-segments/0/").status_code, 404)
        self.assertEqual(FlightSegment.objects.count(), 0)

    def test_member_can_add(self):
        member = User.objects.create_user(username="m@example.com", email="m@example.com")
        TripMember.objects.create(trip=self.trip, user=member)
        self.client.force_authenticate(member)
        self.assertEqual(self.apply(flight=ROUND, reflect=False).status_code, 200)

    def test_login_and_feature_switch(self):
        with override_settings(RESERVATION_ANALYSIS_ENABLED=False):
            self.assertEqual(self.preview(flight=ROUND).status_code, 404)
            self.assertEqual(self.apply(flight=ROUND).status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.preview(flight=ROUND).status_code, (401, 403))
