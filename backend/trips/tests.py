from django.contrib.auth import get_user_model
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
