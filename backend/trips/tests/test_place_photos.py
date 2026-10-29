"""
여행 경로 장소 대표 사진

- 사진은 저장된 place_id로만 조회한다(이름 검색 없음). 사진이 없거나 상한·오류여도 200으로 '사진 없음'을 돌려준다.
- Place Details는 `photos`만 요청하고(무료 등급), 사진 파일 요청(과금)은 월 상한을 넘기 전에 막는다.
- 내가 볼 수 있는 여행 일정에 있는 장소(항공편 제외)의 place_id만 조회할 수 있다.
- 새로 만드는 숙소 카드에는 숙소의 place_id가 복사된다.
"""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .. import place_photos, places, registration
from ..models import Hotel, ItineraryItem, PlacePhotoUsage, Trip, TripMember

User = get_user_model()

PHOTO_NAME = "places/ChIJabc/photos/AUc7tXy"
DETAILS = {
    "photos": [
        {
            "name": PHOTO_NAME,
            "widthPx": 4000,
            "heightPx": 3000,
            "googleMapsUri": "https://www.google.com/maps/place/?photo=abc",
            "authorAttributions": [{"displayName": "김여행", "uri": "https://maps.google.com/maps/contrib/123", "photoUri": "x"}],
        },
        {"name": "places/ChIJabc/photos/second", "authorAttributions": []},
    ]
}
PHOTO_URI = "https://lh3.googleusercontent.com/places/AUc7tXy=s192"


class PlacePhotoTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        self.guest = User.objects.create_user(username="guest@example.com", email="guest@example.com")
        self.stranger = User.objects.create_user(username="stranger@example.com", email="stranger@example.com")
        self.trip = Trip.objects.create(
            owner=self.owner,
            destinations=[{"city": "도쿄", "city_code": "tokyo"}],
            start_date="2026-11-10",
            end_date="2026-11-12",
            itinerary_initialized=True,
        )
        TripMember.objects.create(trip=self.trip, user=self.guest)
        self.place(place_id="ChIJabc")
        self.client.force_authenticate(self.owner)

        def fake_request(url, field_mask, body=None):
            self.calls.append((url, field_mask))
            return self.media if "/media" in url else self.details

        self.calls = []
        self.details = DETAILS
        self.media = {"name": f"{PHOTO_NAME}/photoUri", "photoUri": PHOTO_URI}
        patcher = mock.patch("trips.places._request", side_effect=fake_request)
        self.request = patcher.start()
        self.addCleanup(patcher.stop)
        settings_override = override_settings(PLACE_PHOTO_MONTHLY_LIMIT=900)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def place(self, place_id="ChIJabc", kind="sight", trip=None, title="센소지"):
        return ItineraryItem.objects.create(
            trip=trip or self.trip, day="2026-11-10", order=0, kind=kind, title=title, place_id=place_id
        )

    def get(self, place_id="ChIJabc"):
        return self.client.get("/api/v1/places/photo/", {"place_id": place_id})

    @property
    def media_calls(self):
        return [call for call in self.calls if "/media" in call[0]]


class LookupTests(PlacePhotoTestBase):
    def test_returns_photo_uri_and_author(self):
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["photo_uri"], PHOTO_URI)
        self.assertEqual(response.data["attributions"], [{"name": "김여행", "uri": "https://maps.google.com/maps/contrib/123"}])
        self.assertEqual(response.data["maps_uri"], "https://www.google.com/maps/place/?photo=abc")  # 사진 원본 링크

    def test_uses_the_first_photo_and_only_the_free_details_field(self):
        self.get()
        details_call, media_call = self.calls
        self.assertEqual(details_call, ("https://places.googleapis.com/v1/places/ChIJabc", "photos"))  # 무료 등급 필드만
        self.assertIn(f"/{PHOTO_NAME}/media?", media_call[0])  # 첫 번째 사진
        self.assertIn("skipHttpRedirect=true", media_call[0])
        self.assertIn("maxHeightPx=360", media_call[0])
        self.assertIsNone(media_call[1])  # 사진 파일 요청에는 필드 마스크가 없다.
        self.assertNotIn("key=", media_call[0])  # 키는 헤더로만 보낸다.

    def test_photo_without_author_has_empty_attributions(self):
        self.details = {"photos": [{"name": PHOTO_NAME, "authorAttributions": []}]}
        data = self.get().data
        self.assertEqual((data["attributions"], data["maps_uri"]), ([], ""))

    def test_unsafe_author_link_is_dropped(self):
        self.details = {"photos": [{"name": PHOTO_NAME, "authorAttributions": [{"displayName": "작성자", "uri": "javascript:alert(1)"}]}]}
        self.assertEqual(self.get().data["attributions"], [{"name": "작성자", "uri": ""}])

    def test_place_without_photos_is_none_and_not_billed(self):
        self.details = {}
        data = self.get().data
        self.assertEqual((data["status"], data["photo_uri"]), ("none", None))
        self.assertEqual(self.media_calls, [])  # 과금 호출을 하지 않는다.
        self.assertEqual(PlacePhotoUsage.objects.count(), 0)

    def test_invalid_photo_names_are_ignored(self):
        self.details = {"photos": [{"name": "places/x/photos/../../admin"}, {"name": "https://evil.example/a"}]}
        self.assertEqual(self.get().data["status"], "none")
        self.assertEqual(self.media_calls, [])

    def test_media_without_uri_is_none(self):
        self.media = {}
        self.assertEqual(self.get().data["status"], "none")

    def test_google_errors_never_break_the_response(self):
        self.request.side_effect = places.PlacesError("실패")
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.data["status"], response.data["photo_uri"]), ("error", None))
        self.assertEqual(response["Cache-Control"], "no-store")  # 오류는 브라우저에도 남기지 않는다.

    def test_missing_api_key_is_an_error_result(self):
        with mock.patch("trips.places._request", side_effect=places.PlacesError("키 없음", status_code=503)):
            self.assertEqual(self.get().data["status"], "error")

    def test_browser_may_reuse_the_response_for_one_hour(self):
        self.assertEqual(self.get()["Cache-Control"], "private, max-age=3600")
        self.details = {}
        self.assertEqual(self.get()["Cache-Control"], "private, max-age=3600")

    def test_server_stores_no_photo_data(self):
        self.get()
        self.assertEqual(self.get().data["photo_uri"], PHOTO_URI)
        self.assertEqual(len(self.media_calls), 2)  # 서버는 저장·재사용하지 않고 매번 새로 받는다.
        self.assertFalse(any(field in str(ItineraryItem.objects.get().__dict__) for field in (PHOTO_NAME, PHOTO_URI)))


class MonthlyLimitTests(PlacePhotoTestBase):
    @override_settings(PLACE_PHOTO_MONTHLY_LIMIT=2)
    def test_stops_before_exceeding_the_limit(self):
        self.assertEqual([self.get().data["status"] for _ in range(4)], ["ok", "ok", "limit", "limit"])
        self.assertEqual(len(self.media_calls), 2)  # 상한을 넘는 과금 호출은 하지 않는다.
        self.assertEqual(PlacePhotoUsage.objects.get().count, 2)
        calls_before = len(self.calls)
        self.get()
        self.assertEqual(len(self.calls), calls_before)  # 상한이면 무료인 Details도 부르지 않는다.

    @override_settings(PLACE_PHOTO_MONTHLY_LIMIT=2)
    def test_limit_response_has_no_photo(self):
        PlacePhotoUsage.objects.create(month=place_photos.current_month(), count=2)
        data = self.get().data
        self.assertEqual((data["status"], data["photo_uri"], data["attributions"], data["maps_uri"]), ("limit", None, [], ""))

    @override_settings(PLACE_PHOTO_MONTHLY_LIMIT=0)
    def test_zero_turns_the_feature_off(self):
        self.assertEqual(self.get().data["status"], "limit")
        self.assertEqual(self.calls, [])

    @override_settings(PLACE_PHOTO_MONTHLY_LIMIT=1)
    def test_counts_by_month_in_billing_timezone(self):
        with mock.patch("trips.place_photos.current_month", return_value="2026-10"):
            self.assertEqual(self.get().data["status"], "ok")
            self.assertEqual(self.get().data["status"], "limit")
        with mock.patch("trips.place_photos.current_month", return_value="2026-11"):  # 달이 바뀌면 다시 쓸 수 있다.
            self.assertEqual(self.get().data["status"], "ok")
        self.assertEqual(dict(PlacePhotoUsage.objects.values_list("month", "count")), {"2026-10": 1, "2026-11": 1})

    def test_month_key_uses_pacific_time(self):
        from datetime import datetime, timezone as dt_timezone

        with mock.patch("trips.place_photos.timezone.now", return_value=datetime(2026, 11, 1, 3, 0, tzinfo=dt_timezone.utc)):
            self.assertEqual(place_photos.current_month(), "2026-10")  # UTC로는 11월 1일이지만 태평양 시간은 10월 31일
        with mock.patch("trips.place_photos.timezone.now", return_value=datetime(2026, 11, 1, 9, 0, tzinfo=dt_timezone.utc)):
            self.assertEqual(place_photos.current_month(), "2026-11")

    @override_settings(PLACE_PHOTO_MONTHLY_LIMIT=3)
    def test_failed_photo_request_still_counts(self):
        def fail_on_media(url, field_mask, body=None):
            if "/media" in url:
                raise places.PlacesError("실패")
            return self.details

        self.request.side_effect = fail_on_media
        self.assertEqual(self.get().data["status"], "error")
        self.assertEqual(PlacePhotoUsage.objects.get().count, 1)  # 보수적으로 센다.

    def test_reserve_call_is_atomic_at_the_boundary(self):
        with override_settings(PLACE_PHOTO_MONTHLY_LIMIT=3):
            self.assertEqual([place_photos.reserve_call() for _ in range(5)], [True, True, True, False, False])
            self.assertEqual(place_photos.used_this_month(), 3)


class AccessTests(PlacePhotoTestBase):
    def test_stranger_cannot_lookup_a_place_of_someone_elses_trip(self):
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.get().status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.calls, [])  # Google도 부르지 않는다.

    def test_member_can(self):
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.get().data["status"], "ok")

    def test_unknown_place_id_is_rejected(self):
        self.assertEqual(self.get("ChIJother").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.calls, [])

    def test_flight_cards_are_excluded(self):
        ItineraryItem.objects.all().delete()
        self.place(kind="flight")
        self.assertEqual(self.get().status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_place_id(self):
        for value in ("", "a b", "a/b", "../x", "x" * 256, "한글"):
            self.assertEqual(self.get(value).status_code, status.HTTP_400_BAD_REQUEST, value)

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)
        self.assertIn(self.get().status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(self.calls, [])

    def test_same_place_in_several_cards_is_one_lookup(self):
        self.place(title="센소지 2")  # 같은 장소가 여러 일정에 있어도 한 번 물어보면 된다.
        self.assertEqual(self.get().status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.media_calls), 1)


class HotelCardPlaceIdTests(APITestCase):
    def test_new_hotel_cards_copy_the_place_id(self):
        owner = User.objects.create_user(username="o@example.com", email="o@example.com")
        trip = Trip.objects.create(owner=owner, start_date=date(2026, 11, 10), end_date=date(2026, 11, 13))
        hotel = Hotel.objects.create(trip=trip, name="신주쿠 호텔", address="주소", place_id="ChIJhotel",
                                     check_in=date(2026, 11, 10), check_out=date(2026, 11, 13))
        cards = registration.hotel_cards(trip, hotel)
        self.assertEqual([c["time_label"] for c in cards], ["체크인", "숙박", "숙박", "체크아웃"])
        self.assertEqual({c["place_id"] for c in cards}, {"ChIJhotel"})
        manual = Hotel.objects.create(trip=trip, name="직접 입력 호텔", check_in=date(2026, 11, 10), check_out=date(2026, 11, 11))
        self.assertEqual({c["place_id"] for c in registration.hotel_cards(trip, manual)}, {""})  # place_id가 없는 숙소는 빈 값
