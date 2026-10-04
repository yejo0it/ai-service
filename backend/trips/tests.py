from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Trip

User = get_user_model()


class OnboardingAPITests(APITestCase):
    """온보딩 Step 1~3의 단일 요청 / 단계별 저장 경로를 검증한다."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        self.client.force_authenticate(self.user)

    def test_creates_trip_with_flight_and_hotel_in_one_request(self):
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [
                    {"city": "도쿄", "city_code": "TYO"},
                    {"city": "오사카", "city_code": "OSA"},
                ],
                "start_date": "2026-09-01",
                "end_date": "2026-09-05",
                "flight_info": {
                    "airline": "대한항공",
                    "flight_number": "KE001",
                    "departure_at": "2026-09-01T10:30",
                    "return_arrival_at": "2026-09-05T18:00",
                },
                "hotels": [
                    {
                        "name": "신주쿠 호텔",
                        "address": "도쿄도 신주쿠구",
                        "check_in": "2026-09-01",
                        "check_out": "2026-09-04",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["date_source"], Trip.DateSource.FLIGHT)
        self.assertEqual(response.data["nights"], 4)
        self.assertEqual(len(response.data["hotels"]), 1)

        # 여행지는 입력 순서대로 list[dict] 그대로 저장/응답된다.
        trip = Trip.objects.get(pk=response.data["id"])
        self.assertEqual(
            trip.destinations,
            [
                {"city": "도쿄", "city_code": "TYO"},
                {"city": "오사카", "city_code": "OSA"},
            ],
        )
        self.assertEqual(response.data["destinations"], trip.destinations)
        self.assertEqual(response.data["destination_label"], "도쿄 → 오사카")

    def test_saves_selected_airports_in_flight_info(self):
        airports = {
            "departure_airport": {"code": "ICN", "name": "인천공항 2터미널"},
            "arrival_airport": {"code": "NRT", "name": "나리타공항"},
            "return_departure_airport": {"code": "HND", "name": "하네다공항"},
            "return_arrival_airport": None,
        }
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [{"city": "도쿄", "city_code": "TYO"}],
                "flight_info": {
                    "flight_number": "KE703",
                    "departure_at": "2026-10-12T09:00",
                    "return_arrival_at": "2026-10-17T18:00",
                    **airports,
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        for field, value in airports.items():
            self.assertEqual(response.data["flight_info"][field], value)

    def test_derives_dates_from_flight_info(self):
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [{"city": "오사카", "city_code": "OSA"}],
                "flight_info": {
                    "flight_number": "KE723",
                    "departure_at": "2026-10-02T09:00",
                    "return_arrival_at": "2026-10-06T21:40",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["start_date"], "2026-10-02")
        self.assertEqual(response.data["end_date"], "2026-10-06")

    def test_creates_trip_with_dates_only_and_skipped_hotel(self):
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [{"city": "파리", "city_code": "PAR"}],
                "start_date": "2026-11-01",
                "end_date": "2026-11-07",
                "flight_info": None,
                "hotels": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["date_source"], Trip.DateSource.MANUAL)
        self.assertFalse(response.data["has_flight"])

    def test_adds_hotel_to_existing_trip(self):
        trip = Trip.objects.create(
            owner=self.user,
            destinations=[{"city": "파리", "city_code": "PAR"}],
            start_date="2026-11-01",
            end_date="2026-11-07",
        )
        response = self.client.post(
            f"/api/v1/trips/{trip.pk}/hotels/",
            {
                "name": "파리 아파트",
                "address": "Rue de Rivoli",
                "check_in": "2026-11-01",
                "check_out": None,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["trip"], trip.pk)
        self.assertEqual(trip.hotels.count(), 1)

    def test_rejects_missing_dates(self):
        response = self.client.post(
            "/api/v1/trips/", {"destinations": [{"city": "제주", "city_code": "CJU"}]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_date", response.data)
        self.assertIn("end_date", response.data)

    def test_rejects_end_date_before_start_date(self):
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [{"city": "방콕", "city_code": "BKK"}],
                "start_date": "2026-12-10",
                "end_date": "2026-12-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_date", response.data)

    def test_rejects_hotel_outside_trip_range(self):
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [{"city": "다낭", "city_code": "DAD"}],
                "start_date": "2026-12-01",
                "end_date": "2026-12-05",
                "hotels": [
                    {
                        "name": "리조트",
                        "address": "My Khe",
                        "check_in": "2026-12-04",
                        "check_out": "2026-12-09",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hotels", response.data)

    def test_rejects_empty_destinations(self):
        for payload in ({"destinations": []}, {}):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/v1/trips/",
                    {**payload, "start_date": "2026-12-01", "end_date": "2026-12-05"},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("destinations", response.data)

    def test_accepts_destination_without_city_code(self):
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [{"city": " 후쿠오카 "}],
                "start_date": "2026-12-01",
                "end_date": "2026-12-05",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["destinations"], [{"city": "후쿠오카", "city_code": ""}]
        )

    def test_patches_destinations_on_existing_trip(self):
        trip = Trip.objects.create(
            owner=self.user,
            destinations=[{"city": "도쿄", "city_code": "TYO"}],
            start_date="2026-11-01",
            end_date="2026-11-07",
        )
        response = self.client.patch(
            f"/api/v1/trips/{trip.pk}/",
            {
                "destinations": [
                    {"city": "도쿄", "city_code": "TYO"},
                    {"city": "나고야", "city_code": "ngo"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        trip.refresh_from_db()
        self.assertEqual(
            trip.destinations,
            [
                {"city": "도쿄", "city_code": "TYO"},
                {"city": "나고야", "city_code": "NGO"},
            ],
        )

    def test_filters_trips_by_destination(self):
        Trip.objects.create(
            owner=self.user,
            destinations=[{"city": "도쿄", "city_code": "TYO"}],
            start_date="2026-11-01",
            end_date="2026-11-07",
        )
        Trip.objects.create(
            owner=self.user,
            destinations=[{"city": "파리", "city_code": "PAR"}],
            start_date="2026-11-01",
            end_date="2026-11-07",
        )
        response = self.client.get("/api/v1/trips/", {"destination": "도쿄"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["destinations"],
            [{"city": "도쿄", "city_code": "TYO"}],
        )


class TripOwnershipTests(APITestCase):
    """여행은 만든 회원만 조회·수정할 수 있다."""

    def setUp(self):
        self.user = User.objects.create_user(username="me@example.com", email="me@example.com")
        self.other = User.objects.create_user(username="other@example.com", email="other@example.com")
        self.others_trip = Trip.objects.create(
            owner=self.other,
            destinations=[{"city": "파리", "city_code": "PAR"}],
            start_date="2026-11-01",
            end_date="2026-11-07",
        )
        self.client.force_authenticate(self.user)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/trips/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_created_trip_belongs_to_requester_and_lists_only_mine(self):
        response = self.client.post(
            "/api/v1/trips/",
            {
                "destinations": [{"city": "도쿄", "city_code": "TYO"}],
                "start_date": "2026-10-26",
                "end_date": "2026-10-30",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Trip.objects.get(pk=response.data["id"]).owner, self.user)

        response = self.client.get("/api/v1/trips/")
        self.assertEqual([trip["id"] for trip in response.data], [response.data[0]["id"]])
        self.assertNotEqual(response.data[0]["id"], self.others_trip.pk)

    def test_updates_trip_color(self):
        trip = Trip.objects.create(
            owner=self.user,
            destinations=[{"city": "도쿄", "city_code": "TYO"}],
            start_date="2026-10-12",
            end_date="2026-10-17",
        )
        self.assertEqual(self.client.get(f"/api/v1/trips/{trip.pk}/").data["color"], "")

        response = self.client.patch(f"/api/v1/trips/{trip.pk}/", {"color": "green"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["color"], "green")

        # 빈 값으로 되돌리면 자동 색상이다.
        response = self.client.patch(f"/api/v1/trips/{trip.pk}/", {"color": ""}, format="json")
        self.assertEqual(response.data["color"], "")

        response = self.client.patch(f"/api/v1/trips/{trip.pk}/", {"color": "pink"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deletes_own_trip_but_not_others(self):
        mine = Trip.objects.create(
            owner=self.user,
            destinations=[{"city": "도쿄", "city_code": "TYO"}],
            start_date="2026-10-12",
            end_date="2026-10-17",
        )
        response = self.client.delete(f"/api/v1/trips/{mine.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Trip.objects.filter(pk=mine.pk).exists())

        response = self.client.delete(f"/api/v1/trips/{self.others_trip.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Trip.objects.filter(pk=self.others_trip.pk).exists())

    def test_cannot_read_or_add_hotel_to_others_trip(self):
        self.assertEqual(
            self.client.get(f"/api/v1/trips/{self.others_trip.pk}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        response = self.client.post(
            "/api/v1/hotels/",
            {"trip": self.others_trip.pk, "name": "호텔", "address": "파리", "check_in": "2026-11-01"},
            format="json",
        )
        # 다른 회원의 여행은 없는 여행으로 취급한다.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(self.others_trip.hotels.exists())


class TravelInfoTests(APITestCase):
    """홈 위젯의 날씨·환율. 외부 API 응답은 모킹한다."""

    OPEN_METEO = {
        "current": {"temperature_2m": 21.4, "weather_code": 1},
        "daily": {
            "time": ["2026-10-12", "2026-10-13"],
            "weather_code": [1, 61],
            "temperature_2m_max": [22.0, 19.5],
            "temperature_2m_min": [15.1, 14.0],
        },
    }
    ER_API = {"result": "success", "time_last_update_utc": "Tue, 29 Sep 2026", "rates": {"JPY": 0.1124, "EUR": 0.00064}}

    def setUp(self):
        cache.clear()
        self.client.force_authenticate(User.objects.create_user(username="info@example.com"))

    def test_weather_for_city(self):
        with mock.patch("trips.travel_info._get_json", return_value=self.OPEN_METEO) as get_json:
            response = self.client.get("/api/v1/travel-info/weather/", {"city_code": "tyo"})
            self.client.get("/api/v1/travel-info/weather/", {"city_code": "TYO"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current"], {"temperature": 21.4, "weather_code": 1})
        self.assertEqual(response.data["daily"][1], {"date": "2026-10-13", "weather_code": 61, "max": 19.5, "min": 14.0})
        # 두 번째 요청은 캐시에서 돌려준다.
        self.assertEqual(get_json.call_count, 1)

    def test_weather_unknown_city(self):
        response = self.client.get("/api/v1/travel-info/weather/", {"city_code": "XXX"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_exchange_rates_per_currency_unit(self):
        with mock.patch("trips.travel_info._get_json", return_value=self.ER_API):
            response = self.client.get(
                "/api/v1/travel-info/exchange-rates/", {"city_codes": "SEL,TYO,OSA,PAR"}
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 국내(원화)는 빼고, 같은 통화(도쿄·오사카)는 한 번만. 엔은 100엔 단위.
        self.assertEqual(
            [(rate["currency"], rate["unit"], rate["krw"]) for rate in response.data["rates"]],
            [("JPY", 100, 889.68), ("EUR", 1, 1562.5)],
        )

    def test_requires_login(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/v1/travel-info/weather/", {"city_code": "TYO"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
