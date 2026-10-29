"""
예약 정보로 여행 만들기(2단계)

- 1단계에서 확인·수정한 예약 정보(항공권 필수·숙소 선택)를 서버가 다시 검증하고, 여행·비행 구간·숙소를 한 번에 만든다.
- 비행 구간은 FlightSegment로 저장하고 Trip.flight_info에 요약(첫 가는 편·마지막 오는 편)을 함께 저장해 기존 화면이 그대로 동작한다.
- 같은 요청 번호로 다시 보내면 여행을 하나만 만든다. 하나라도 틀리면 아무것도 저장하지 않는다.
- 예약 정보로 등록한 항공편은 AI·경로 카드·여행 수정으로 바꾸지 않는다(숙소·일정은 그대로 바꿀 수 있다).
- AI·외부 API를 부르지 않는다.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .. import ai_planner
from ..models import FlightSegment, Hotel, ItineraryItem, Trip, TripMember
from ..reservations import trips as reservation_trips

User = get_user_model()
URL = "/api/v1/trips/from-reservations/"


def segment(number, dep, arr, dep_date, dep_time, arr_date, arr_time, direction=None, airline="대한항공"):
    return {
        "airline_name": airline, "flight_number": number,
        "departure_airport_code": dep, "departure_airport_name": f"{dep} 공항",
        "arrival_airport_code": arr, "arrival_airport_name": f"{arr} 공항",
        "departure_date": dep_date, "departure_time": dep_time,
        "arrival_date": arr_date, "arrival_time": arr_time, "direction": direction, "notes": [],
    }


ROUND_TRIP = {"itineraries": [{"status": "확정", "segments": [
    segment("KE703", "ICN", "NRT", "2026-11-10", "09:05", "2026-11-10", "11:20", "outbound"),
    segment("KE704", "NRT", "ICN", "2026-11-14", "18:40", "2026-11-14", "21:15", "return"),
]}]}

STAYS = {"stays": [
    {"name": "신주쿠 호텔", "address": "도쿄 신주쿠구 1-1", "check_in_date": "2026-11-10", "check_out_date": "2026-11-12",
     "check_in_time": "15:00", "check_out_time": "11:00", "status": "확정", "notes": []},
    {"name": "아사쿠사 료칸", "address": None, "check_in_date": "2026-11-12", "check_out_date": "2026-11-14",
     "check_in_time": None, "check_out_time": None, "status": None, "notes": []},
]}


def body(**changes):
    data = {
        "request_id": "req-0001-abcdef",
        "flight": ROUND_TRIP,
        "hotels": STAYS,
        "start_date": "2026-11-10",
        "end_date": "2026-11-14",
        "destinations": [{"city": "도쿄", "city_code": "tokyo"}],
    }
    data.update(changes)
    return data


@override_settings(RESERVATION_ANALYSIS_ENABLED=True)
class TripFromReservationTestBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="u@example.com", email="u@example.com")
        self.client.force_authenticate(self.user)
        # AI·외부 API는 절대 부르지 않는다.
        for target in ("trips.reservations.extract.anthropic.Anthropic", "trips.places._request", "trips.travel_info._get_json"):
            patcher = mock.patch(target, side_effect=AssertionError(f"{target} 호출 금지"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def create(self, **changes):
        return self.client.post(URL, body(**changes), format="json")


class CreateTripTests(TripFromReservationTestBase):
    def test_creates_trip_segments_and_hotels(self):
        response = self.create()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        trip = Trip.objects.get()
        self.assertEqual((trip.owner, str(trip.start_date), str(trip.end_date), trip.date_source), (self.user, "2026-11-10", "2026-11-14", "flight"))
        self.assertEqual(trip.destinations, [{"city": "도쿄", "city_code": "tokyo"}])
        self.assertEqual(
            list(trip.flight_segments.values_list("order", "direction", "flight_number", "departure_airport_code", "arrival_airport_code")),
            [(0, "outbound", "KE703", "ICN", "NRT"), (1, "return", "KE704", "NRT", "ICN")],
        )
        hotels = list(trip.hotels.order_by("check_in"))
        self.assertEqual([(h.name, str(h.check_in), str(h.check_out)) for h in hotels],
                         [("신주쿠 호텔", "2026-11-10", "2026-11-12"), ("아사쿠사 료칸", "2026-11-12", "2026-11-14")])
        self.assertEqual((str(hotels[0].check_in_time), str(hotels[0].check_out_time)), ("15:00:00", "11:00:00"))
        self.assertEqual((hotels[1].check_in_time, hotels[1].address), (None, ""))  # 없는 값은 비워 둔다(임의로 채우지 않음).
        self.assertFalse(trip.itinerary_items.exists())  # 경로 카드는 상세를 처음 열 때 만든다(관광 일정 없음).

    def test_flight_info_summary_keeps_existing_screens_working(self):
        data = self.create().data
        info = data["flight_info"]
        self.assertEqual((info["flight_number"], info["departure_at"][:16], info["arrival_at"][:16]), ("KE703", "2026-11-10T09:05", "2026-11-10T11:20"))
        self.assertEqual((info["departure_airport"]["code"], info["arrival_airport"]["code"]), ("ICN", "NRT"))
        self.assertEqual((info["return_flight_number"], info["return_departure_at"][:16], info["return_arrival_at"][:16]),
                         ("KE704", "2026-11-14T18:40", "2026-11-14T21:15"))
        self.assertEqual((info["return_departure_airport"]["code"], info["return_arrival_airport"]["code"]), ("NRT", "ICN"))
        self.assertTrue(data["has_flight"])
        self.assertEqual([s["flight_number"] for s in data["flight_segments"]], ["KE703", "KE704"])
        self.assertEqual(data["flight_segments"][0]["departure_time"], "09:05")
        self.assertEqual(data["hotels"][0]["check_in_time"], "15:00")

    def test_hotels_are_optional(self):
        response = self.create(hotels=None)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Hotel.objects.exists())

    def test_layover_and_multi_city_segments_are_kept_in_order(self):
        multi = {"itineraries": [{"status": None, "segments": [
            segment("NH862", "ICN", "HND", "2026-12-20", "21:30", "2026-12-20", "23:55"),
            segment("NH184", "HND", "HNL", "2026-12-21", "00:50", "2026-12-20", "12:35"),  # 날짜변경선
            segment("NH183", "HNL", "HND", "2026-12-27", "12:30", "2026-12-28", "16:20"),
            segment("NH863", "HND", "ICN", "2026-12-28", "20:00", "2026-12-28", "22:40"),
        ]}]}
        response = self.create(flight=multi, hotels=None, start_date="2026-12-20", end_date="2026-12-28",
                               destinations=[{"city": "호놀룰루", "city_code": ""}])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        segments = list(FlightSegment.objects.values_list("flight_number", "direction"))
        # 방향을 모르면 가장 오래 머문 곳(호놀룰루)을 기준으로 가는 편·오는 편을 나눈다.
        self.assertEqual(segments, [("NH862", "outbound"), ("NH184", "outbound"), ("NH183", "return"), ("NH863", "return")])
        info = Trip.objects.get().flight_info
        self.assertEqual((info["departure_airport"]["code"], info["arrival_airport"]["code"]), ("ICN", "HNL"))  # 경유 후 최종 도착지
        self.assertEqual((info["return_departure_airport"]["code"], info["return_arrival_airport"]["code"]), ("HNL", "ICN"))
        self.assertIn("경유", info["note"])

    def test_one_way_has_no_return(self):
        one_way = {"itineraries": [{"status": None, "segments": [
            segment("JL3", "HND", "FUK", "2026-11-05", "08:00", "2026-11-05", "09:50"),
            segment("JL951", "FUK", "ICN", "2026-11-05", "11:30", "2026-11-05", "13:00"),
        ]}]}
        response = self.create(flight=one_way, hotels=None, start_date="2026-11-05", end_date="2026-11-05")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("return_flight_number", Trip.objects.get().flight_info)
        self.assertEqual(set(FlightSegment.objects.values_list("direction", flat=True)), {"outbound"})

    def test_segments_from_several_bookings_are_sorted_by_departure(self):
        two_bookings = {"itineraries": [
            {"status": None, "segments": [segment("KE704", "NRT", "ICN", "2026-11-14", "18:40", "2026-11-14", "21:15", "return")]},
            {"status": None, "segments": [segment("KE703", "ICN", "NRT", "2026-11-10", "09:05", "2026-11-10", "11:20", "outbound")]},
        ]}
        self.create(flight=two_bookings)
        self.assertEqual(list(FlightSegment.objects.values_list("flight_number", flat=True)), ["KE703", "KE704"])

    def test_hotel_place_and_city_from_hotel_search(self):
        places = [{"place_id": "ChIJhotel", "latitude": 35.69, "longitude": 139.70, "address": "신주쿠 정확한 주소", "phone": "03-1234-5678"}, None]
        self.create(hotel_places=places, hotel_cities=["tokyo", ""])
        first, second = Hotel.objects.order_by("check_in")
        self.assertEqual((first.place_id, first.latitude, first.address, first.phone, first.city_code),
                         ("ChIJhotel", 35.69, "신주쿠 정확한 주소", "03-1234-5678", "tokyo"))
        self.assertEqual((second.place_id, second.latitude), ("", None))


class ValidationTests(TripFromReservationTestBase):
    def assert_nothing_saved(self):
        self.assertEqual((Trip.objects.count(), FlightSegment.objects.count(), Hotel.objects.count()), (0, 0, 0))

    def test_flight_is_required_and_rechecked(self):
        broken = {"itineraries": [{"status": None, "segments": [segment(None, "ICN", "NRT", "2026-11-10", "09:05", None, None)]}]}
        for flight in ({}, {"itineraries": []}, broken):
            response = self.create(flight=flight)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, flight)
            self.assertIn("flight", response.data)
        self.assertEqual(self.client.post(URL, {k: v for k, v in body().items() if k != "flight"}, format="json").status_code, 400)
        self.assert_nothing_saved()

    def test_invalid_hotel_saves_nothing(self):
        bad = {"stays": [dict(STAYS["stays"][0], check_out_date="2026-11-09")]}
        response = self.create(hotels=bad)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hotels", response.data)
        self.assert_nothing_saved()

    def test_dates_must_cover_the_flights_and_hotels(self):
        cases = [
            dict(start_date="2026-11-11"),  # 가는 편이 기간 밖
            dict(end_date="2026-11-13"),  # 오는 편·숙소가 기간 밖
            dict(start_date="2026-11-14", end_date="2026-11-10"),  # 순서
        ]
        for changes in cases:
            self.assertEqual(self.create(**changes).status_code, status.HTTP_400_BAD_REQUEST, changes)
        self.assert_nothing_saved()

    def test_destinations_are_required(self):
        self.assertEqual(self.create(destinations=[]).status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_nothing_saved()

    def test_bad_request_id_and_place_values(self):
        self.assertEqual(self.create(request_id="x").status_code, 400)
        self.assertEqual(self.create(hotel_places=[{"latitude": 200}]).status_code, 400)
        self.assert_nothing_saved()

    def test_failure_after_trip_is_created_rolls_everything_back(self):
        with mock.patch.object(FlightSegment.objects, "bulk_create", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assert_nothing_saved()


class DuplicateTests(TripFromReservationTestBase):
    def test_same_request_id_creates_one_trip(self):
        first = self.create()
        again = self.create()
        self.assertEqual((first.status_code, again.status_code), (status.HTTP_201_CREATED, status.HTTP_200_OK))
        self.assertEqual(first.data["id"], again.data["id"])
        self.assertEqual((Trip.objects.count(), FlightSegment.objects.count(), Hotel.objects.count()), (1, 2, 2))

    def test_different_request_ids_create_separate_trips(self):
        self.create()
        self.create(request_id="req-0002-abcdef")
        self.assertEqual(Trip.objects.count(), 2)

    def test_request_id_is_per_user(self):
        self.create()
        other = User.objects.create_user(username="o@example.com", email="o@example.com")
        self.client.force_authenticate(other)
        response = self.create()  # 다른 사람이 같은 번호를 보내도 그 사람의 여행을 보여 주지 않는다.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Trip.objects.filter(owner=other).count(), 0)


class AccessTests(TripFromReservationTestBase):
    def test_login_required(self):
        self.client.force_authenticate(None)
        self.assertIn(self.create().status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertFalse(Trip.objects.exists())

    def test_hidden_when_reservation_feature_is_off(self):
        with override_settings(RESERVATION_ANALYSIS_ENABLED=False):
            self.assertEqual(self.create().status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.get("/api/v1/reservations/config/").data, {"enabled": False})
        self.assertEqual(self.client.get("/api/v1/reservations/config/").data, {"enabled": True})
        self.assertFalse(Trip.objects.exists())

    def test_created_trip_is_private_to_owner_and_members(self):
        trip_id = self.create().data["id"]
        stranger = User.objects.create_user(username="s@example.com", email="s@example.com")
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.get(f"/api/v1/trips/{trip_id}/").status_code, status.HTTP_404_NOT_FOUND)


class FlightLockTests(TripFromReservationTestBase):
    """예약 정보로 등록한 항공편은 AI·경로 카드·여행 수정으로 바꾸지 않는다."""

    def setUp(self):
        super().setUp()
        self.trip = Trip.objects.get(pk=self.create().data["id"])

    def plan(self, **changes):
        fields = dict(reply="바꿨어요.", additions=[], remove_item_ids=[], moves=[], form=None, confirm=None,
                      flight=None, hotel_change=None, off_topic=False)
        fields.update(changes)
        return ai_planner.PlanResponse(**fields)

    def propose(self, plan):
        with mock.patch("trips.ai_planner.propose", return_value=plan):
            return self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                    {"messages": [{"role": "user", "content": "항공편 바꿔 줘"}]}, format="json")

    def test_ai_does_not_propose_flight_changes(self):
        change = ai_planner.FlightChange(mode="replace", outbound=ai_planner.FlightLegInput(
            departure_airport_code="GMP", departure_airport_name="김포", arrival_airport_code="HND", arrival_airport_name="하네다",
            airline="아시아나", flight_number="OZ1085", arrival_time=None, date="2026-11-10"), return_leg=None)
        for plan in (self.plan(flight=change), self.plan(confirm="flight"), self.plan(form="flight")):
            response = self.propose(plan)
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertFalse(response.data["proposal"]["flight_changed"])
            self.assertIn("예약 확인서로 등록", response.data["reply"])

    def test_ai_apply_with_flight_change_is_rejected(self):
        proposal = {"additions": [], "remove_item_ids": [], "moves": [], "flight_changed": True,
                    "flight_info": {"flight_number": "OZ1085", "departure_at": "2026-11-10T08:00:00"}, "hotels": None}
        response = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/apply/", {"proposal": proposal}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.flight_info["flight_number"], "KE703")

    def test_flight_card_cannot_be_deleted_but_hotel_card_can(self):
        flight = ItineraryItem.objects.create(trip=self.trip, day="2026-11-10", order=0, kind="flight", source="auto",
                                              title="가는 편 · KE703", time_label="출국")
        stay = ItineraryItem.objects.create(trip=self.trip, day="2026-11-11", order=0, kind="hotel", source="auto",
                                            title="신주쿠 호텔", time_label="숙박")
        self.assertEqual(self.client.delete(f"/api/v1/itinerary-items/{flight.id}/").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(ItineraryItem.objects.filter(pk=flight.pk).exists())
        self.assertIn(self.client.delete(f"/api/v1/itinerary-items/{stay.id}/").status_code, (200, 204))

    def test_trip_update_cannot_change_flight_info(self):
        response = self.client.patch(f"/api/v1/trips/{self.trip.pk}/", {"flight_info": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.patch(f"/api/v1/trips/{self.trip.pk}/", {"color": "red"}, format="json").status_code, 200)

    def test_members_are_also_blocked(self):
        member = User.objects.create_user(username="m@example.com", email="m@example.com")
        TripMember.objects.create(trip=self.trip, user=member)
        self.client.force_authenticate(member)
        self.assertEqual(self.client.patch(f"/api/v1/trips/{self.trip.pk}/", {"flight_info": None}, format="json").status_code, 400)


class CompatibilityTests(TripFromReservationTestBase):
    def test_direct_trips_are_unchanged(self):
        response = self.client.post("/api/v1/trips/", {
            "destinations": [{"city": "도쿄", "city_code": "tokyo"}], "start_date": "2026-11-10", "end_date": "2026-11-12",
            "flight_info": None, "hotels": [{"name": "호텔", "address": "주소", "check_in": "2026-11-10", "check_out": "2026-11-12"}],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["flight_segments"], [])  # 직접 등록한 여행은 구간이 없다.
        self.assertIsNone(response.data["hotels"][0]["check_in_time"])
        trip = Trip.objects.get(pk=response.data["id"])
        self.assertIsNone(trip.creation_key)
        # 직접 등록한 여행은 지금처럼 항공 정보를 고칠 수 있다.
        flight = {"flight_number": "KE703", "departure_at": "2026-11-10T09:05:00"}
        self.assertEqual(self.client.patch(f"/api/v1/trips/{trip.pk}/", {"flight_info": flight}, format="json").status_code, 200)

    def test_trip_list_includes_segments(self):
        self.create()
        trips = self.client.get("/api/v1/trips/").data
        self.assertEqual(len(trips[0]["flight_segments"]), 2)


class SegmentDirectionTests(APITestCase):
    """방향을 모를 때 가는 편·오는 편 나누기(순수 계산)."""

    def directions(self, *segments):
        document = {"itineraries": [{"status": None, "segments": list(segments)}]}
        return [s["direction"] for s in reservation_trips.flatten_segments(document)]

    def test_round_trip_without_labels(self):
        self.assertEqual(self.directions(
            segment("KE703", "ICN", "NRT", "2026-11-10", "09:05", "2026-11-10", "11:20"),
            segment("KE704", "NRT", "ICN", "2026-11-14", "18:40", "2026-11-14", "21:15"),
        ), ["outbound", "return"])

    def test_short_layover_round_trip_stays_outbound_until_the_long_stay(self):
        self.assertEqual(self.directions(
            segment("A1", "ICN", "HND", "2026-11-10", "09:00", "2026-11-10", "11:00"),
            segment("A2", "HND", "OKA", "2026-11-10", "13:00", "2026-11-10", "15:00"),  # 2시간 환승
            segment("A3", "OKA", "ICN", "2026-11-15", "10:00", "2026-11-15", "12:30"),
        ), ["outbound", "outbound", "return"])

    def test_open_jaw_without_return_to_origin_is_all_outbound(self):
        self.assertEqual(self.directions(
            segment("A1", "ICN", "NRT", "2026-11-10", "09:00", "2026-11-10", "11:00"),
            segment("A2", "KIX", "GMP", "2026-11-15", "10:00", "2026-11-15", "12:00"),
        ), ["outbound", "outbound"])

    def test_same_day_round_trip_splits_at_the_stay(self):
        self.assertEqual(self.directions(
            segment("A1", "GMP", "CJU", "2026-11-10", "07:00", "2026-11-10", "08:10"),
            segment("A2", "CJU", "GMP", "2026-11-10", "20:00", "2026-11-10", "21:10"),
        ), ["outbound", "return"])

    def test_labels_from_the_document_win(self):
        self.assertEqual(self.directions(
            segment("A1", "ICN", "NRT", "2026-11-10", "09:00", "2026-11-10", "11:00", "outbound"),
            segment("A2", "NRT", "ICN", "2026-11-10", "13:00", "2026-11-10", "15:00", "return"),
        ), ["outbound", "return"])
