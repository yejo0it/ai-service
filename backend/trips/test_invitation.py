"""
여행 일행 초대

- 초대 링크: 만든 회원만 발급, 여행마다 하나, 7일 유효, 새로 만들면 이전 링크는 바로 쓸 수 없다.
- 링크 수락: 일행으로 들어와 만든 회원과 똑같이 일정·숙소·체크리스트를 편집한다. 최대 10명.
- 여행 삭제·링크 발급·내보내기는 만든 회원만, 나가기는 일행 본인이 한다.
- 일행이 아닌 회원에게는 여행이 없는 것(404)으로 보인다.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile
from accounts.nickname import NICKNAME_PATTERN

from .models import ChecklistItem, Hotel, ItineraryItem, PackingItem, Trip, TripInvitation, TripMember

User = get_user_model()


class InvitationTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        self.guest = User.objects.create_user(username="guest@example.com", email="guest@example.com")
        Profile.objects.create(user=self.owner, nickname="만든이")
        Profile.objects.create(user=self.guest, nickname="일행")
        self.stranger = User.objects.create_user(username="stranger@example.com", email="stranger@example.com")
        self.trip = Trip.objects.create(owner=self.owner, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True)

    def as_user(self, user):
        self.client.force_authenticate(user)

    def create_link(self, **body):
        self.as_user(self.owner)
        return self.client.post(f"/api/v1/trips/{self.trip.id}/invitations/", body, format="json")

    def accept(self, user, token):
        self.as_user(user)
        return self.client.post(f"/api/v1/trips/invitations/{token}/accept/")


class InvitationLinkTests(InvitationTestBase):
    def test_owner_creates_one_link_for_seven_days(self):
        first = self.create_link()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        expires = TripInvitation.objects.get(trip=self.trip).expires_at
        self.assertAlmostEqual((expires - timezone.now()).total_seconds(), 7 * 86400, delta=60)

        # 쓸 수 있는 링크가 있으면 같은 링크를 돌려준다.
        again = self.create_link()
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(again.data["token"], first.data["token"])
        self.assertEqual(TripInvitation.objects.count(), 1)

    def test_regenerate_invalidates_old_link(self):
        old = self.create_link().data["token"]
        new = self.create_link(regenerate=True).data["token"]
        self.assertNotEqual(old, new)
        self.assertEqual(self.accept(self.guest, old).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.accept(self.guest, new).status_code, status.HTTP_201_CREATED)

    def test_expired_link_is_rejected_and_owner_gets_new_one(self):
        token = self.create_link().data["token"]
        TripInvitation.objects.filter(trip=self.trip).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.accept(self.guest, token)
        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertFalse(TripMember.objects.exists())
        # 만료된 링크는 목록에 나오지 않고, 다시 만들면 새 토큰이 나온다.
        self.as_user(self.owner)
        self.assertIsNone(self.client.get(f"/api/v1/trips/{self.trip.id}/members/").data["invitation"])
        self.assertNotEqual(self.create_link().data["token"], token)

    def test_only_owner_creates_link(self):
        TripMember.objects.create(trip=self.trip, user=self.guest)
        self.as_user(self.guest)
        response = self.client.post(f"/api/v1/trips/{self.trip.id}/invitations/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.as_user(self.stranger)
        response = self.client.post(f"/api/v1/trips/{self.trip.id}/invitations/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_accept_requires_login(self):
        token = self.create_link().data["token"]
        self.client.force_authenticate(None)
        response = self.client.post(f"/api/v1/trips/invitations/{token}/accept/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_accept_adds_member_once(self):
        token = self.create_link().data["token"]
        joined = self.accept(self.guest, token)
        self.assertEqual(joined.status_code, status.HTTP_201_CREATED)
        self.assertEqual(joined.data, {"trip_id": self.trip.id, "joined": True})
        again = self.accept(self.guest, token)
        self.assertEqual(again.data, {"trip_id": self.trip.id, "joined": False})
        self.assertEqual(self.accept(self.owner, token).data, {"trip_id": self.trip.id, "joined": False})
        self.assertEqual(TripMember.objects.filter(trip=self.trip).count(), 1)

    def test_member_limit(self):
        token = self.create_link().data["token"]
        for index in range(TripMember.MAX_PER_TRIP):
            user = User.objects.create_user(username=f"m{index}@example.com", email=f"m{index}@example.com")
            TripMember.objects.create(trip=self.trip, user=user)
        response = self.accept(self.guest, token)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(TripMember.objects.filter(user=self.guest).exists())


class MemberAccessTests(InvitationTestBase):
    def setUp(self):
        super().setUp()
        TripMember.objects.create(trip=self.trip, user=self.guest)
        self.item = ItineraryItem.objects.create(trip=self.trip, day="2026-11-10", order=0, kind="sight",
                                                 source="manual", title="센소지", stops=[])
        self.check = ChecklistItem.objects.create(item=self.item, text="입장권")
        self.hotel = Hotel.objects.create(trip=self.trip, name="숙소", address="", check_in="2026-11-10",
                                          check_out="2026-11-12")

    def test_member_sees_and_edits_trip(self):
        self.as_user(self.guest)
        listed = self.client.get("/api/v1/trips/")
        self.assertEqual([trip["id"] for trip in listed.data], [self.trip.id])
        self.assertFalse(listed.data[0]["is_owner"])
        self.assertEqual(self.client.get(f"/api/v1/trips/{self.trip.id}/itinerary/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/v1/trips/{self.trip.id}/", {"color": "red"}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/v1/itinerary-items/{self.item.id}/", {"memo": "아침"}).status_code,
                         200)
        self.assertEqual(self.client.post(f"/api/v1/itinerary-items/{self.item.id}/checklist/",
                                          {"text": "우산"}).status_code, 201)
        self.assertEqual(self.client.patch(f"/api/v1/checklist-items/{self.check.id}/", {"done": True}).status_code,
                         200)
        self.assertEqual(self.client.patch(f"/api/v1/hotels/{self.hotel.id}/", {"name": "새 숙소"}).status_code,
                         200)
        self.assertEqual(self.client.get(f"/api/v1/trips/{self.trip.id}/packing-note/").status_code, 200)

    def test_owner_flag(self):
        self.as_user(self.owner)
        self.assertTrue(self.client.get(f"/api/v1/trips/{self.trip.id}/").data["is_owner"])

    def test_stranger_cannot_reach_trip(self):
        self.as_user(self.stranger)
        self.assertEqual(self.client.get("/api/v1/trips/").data, [])
        for url in (f"/api/v1/trips/{self.trip.id}/", f"/api/v1/trips/{self.trip.id}/itinerary/",
                    f"/api/v1/trips/{self.trip.id}/members/", f"/api/v1/hotels/{self.hotel.id}/",
                    f"/api/v1/trips/{self.trip.id}/packing-note/"):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND, url)
        self.assertEqual(self.client.patch(f"/api/v1/itinerary-items/{self.item.id}/", {"memo": "x"}).status_code,
                         404)
        self.assertEqual(self.client.patch(f"/api/v1/checklist-items/{self.check.id}/", {"done": True}).status_code,
                         404)
        packing = PackingItem.objects.create(trip=self.trip, text="여권")
        self.assertEqual(self.client.patch(f"/api/v1/packing-items/{packing.id}/", {"done": True}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/trips/{self.trip.id}/members/{self.guest.id}/").status_code,
                         404)

    def test_only_owner_deletes_trip(self):
        self.as_user(self.guest)
        self.assertEqual(self.client.delete(f"/api/v1/trips/{self.trip.id}/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Trip.objects.filter(pk=self.trip.pk).exists())
        self.as_user(self.owner)
        self.assertEqual(self.client.delete(f"/api/v1/trips/{self.trip.id}/").status_code, 204)

    def test_member_list_shows_names_only(self):
        self.as_user(self.guest)
        data = self.client.get(f"/api/v1/trips/{self.trip.id}/members/").data
        self.assertFalse(data["is_owner"])
        self.assertEqual(data["owner"]["name"], "만든이")
        self.assertEqual([(m["id"], m["name"]) for m in data["members"]], [(self.guest.id, "일행")])
        self.assertEqual(data["max_members"], 10)
        self.assertNotIn("guest@example.com", str(data))

    def test_user_without_nickname_gets_random_one_not_email(self):
        # 닉네임이 없는 회원(만든 사람 포함)도 이메일 대신 랜덤 닉네임으로 보인다.
        Profile.objects.filter(user=self.owner).update(nickname="")
        self.as_user(self.guest)
        data = self.client.get(f"/api/v1/trips/{self.trip.id}/members/").data
        self.assertRegex(data["owner"]["name"], NICKNAME_PATTERN)
        self.assertNotIn("owner", data["owner"]["name"])
        self.assertNotIn("owner@example.com", str(data))

    def test_owner_removes_member_and_member_leaves(self):
        other = User.objects.create_user(username="other@example.com", email="other@example.com")
        TripMember.objects.create(trip=self.trip, user=other)

        # 일행은 다른 일행을 내보낼 수 없다.
        self.as_user(self.guest)
        response = self.client.delete(f"/api/v1/trips/{self.trip.id}/members/{other.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 만든 회원이 내보내면 그 회원은 여행을 볼 수 없다.
        self.as_user(self.owner)
        self.assertEqual(self.client.delete(f"/api/v1/trips/{self.trip.id}/members/{other.id}/").status_code, 204)
        self.as_user(other)
        self.assertEqual(self.client.get(f"/api/v1/trips/{self.trip.id}/").status_code, 404)

        # 일행은 스스로 나간다.
        self.as_user(self.guest)
        self.assertEqual(self.client.delete(f"/api/v1/trips/{self.trip.id}/members/{self.guest.id}/").status_code,
                         204)
        self.assertEqual(self.client.get("/api/v1/trips/").data, [])
        self.assertTrue(Trip.objects.filter(pk=self.trip.pk).exists())
