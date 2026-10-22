"""
여행 요약(한 줄 메모·사진 3장)

- 쓰기는 여행 시작일부터 할 수 있다(시작 전에는 403). 조회는 여행 참여자 누구나 한다.
- 사진은 여행당 최대 3장, 5MB 이하 JPG·PNG·WEBP·GIF만 받고 JPEG로 다시 저장한다(EXIF 제거).
- 사진은 공개 주소가 없고 파일 API로만 받으며, 여행 참여자가 아닌 회원에게는 없는 것(404)이다.
- 여행·사진을 지우면 파일도 지운다.
"""

import os
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Trip, TripMember, TripPhoto, TripSummary

User = get_user_model()

def image_file(name="photo.png", size=(800, 600), fmt="PNG", exif_orientation=None):
    buffer = BytesIO()
    image = Image.new("RGB", size, "skyblue")
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        image.save(buffer, format=fmt, exif=exif)
    else:
        image.save(buffer, format=fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


def make_trip(owner, start_offset, end_offset, **extra):
    today = timezone.localdate()
    return Trip.objects.create(
        owner=owner,
        destinations=[{"city": "도쿄", "city_code": "tokyo"}],
        start_date=today + timedelta(days=start_offset),
        end_date=today + timedelta(days=end_offset),
        itinerary_initialized=True,
        **extra,
    )


class SummaryTestBase(APITestCase):
    def setUp(self):
        # 파일은 테스트마다 새 폴더에 저장한다(DB와 달리 파일은 테스트가 끝나도 저절로 지워지지 않는다).
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        override = override_settings(PRIVATE_MEDIA_ROOT=self.root)
        override.enable()
        self.addCleanup(override.disable)
        self.owner = User.objects.create_user(username="owner@example.com", email="owner@example.com")
        self.guest = User.objects.create_user(username="guest@example.com", email="guest@example.com")
        self.stranger = User.objects.create_user(username="stranger@example.com", email="stranger@example.com")
        self.trip = make_trip(self.owner, -1, 1)  # 여행 중
        TripMember.objects.create(trip=self.trip, user=self.guest)
        self.client.force_authenticate(self.owner)

    def summary_url(self, trip=None):
        return f"/api/v1/trips/{(trip or self.trip).id}/summary/"

    def photos_url(self, trip=None):
        return f"/api/v1/trips/{(trip or self.trip).id}/photos/"

    def photo_url(self, photo_id, trip=None):
        return f"/api/v1/trips/{(trip or self.trip).id}/photos/{photo_id}/"

    def upload(self, file=None, trip=None):
        return self.client.post(self.photos_url(trip), {"image": file or image_file()}, format="multipart")

    def stored_files(self):
        return sorted(
            os.path.join(root, name) for root, _, names in os.walk(self.root) for name in names
        )


class WritableFromStartDateTests(SummaryTestBase):
    def test_before_start_reads_work_but_writes_are_rejected(self):
        upcoming = make_trip(self.owner, 1, 3)
        data = self.client.get(self.summary_url(upcoming)).data
        self.assertEqual((data["memo"], data["photos"], data["writable"], data["max_photos"]), ("", [], False, 3))
        self.assertEqual(self.client.put(self.summary_url(upcoming), {"memo": "안녕"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.upload(trip=upcoming).status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(TripSummary.objects.exists() or TripPhoto.objects.exists())

    def test_writable_on_the_start_day_during_and_after_the_trip(self):
        for start, end in ((0, 2), (-3, 1), (-10, -5)):  # 시작일 당일, 여행 중, 종료 후
            trip = make_trip(self.owner, start, end)
            self.assertTrue(self.client.get(self.summary_url(trip)).data["writable"], (start, end))
            self.assertEqual(self.client.put(self.summary_url(trip), {"memo": f"{start}"}, format="json").status_code, status.HTTP_200_OK)
            self.assertEqual(self.upload(trip=trip).status_code, status.HTTP_201_CREATED)

    def test_photo_edits_before_start_are_rejected(self):
        trip = make_trip(self.owner, 1, 3)
        photo = TripPhoto.objects.create(trip=trip, image="trips/x/a.jpg", width=1, height=1, size_bytes=1)
        self.assertEqual(self.client.put(self.photo_url(photo.id, trip), {"image": image_file()}, format="multipart").status_code, 403)
        self.assertEqual(self.client.delete(self.photo_url(photo.id, trip)).status_code, 403)
        self.assertTrue(TripPhoto.objects.filter(pk=photo.pk).exists())


class MemoTests(SummaryTestBase):
    def put(self, memo):
        return self.client.put(self.summary_url(), {"memo": memo}, format="json")

    def test_save_update_and_clear(self):
        self.assertEqual(self.put("  첫날 라멘이 최고였다  ").data["memo"], "첫날 라멘이 최고였다")
        self.assertEqual(self.client.get(self.summary_url()).data["memo"], "첫날 라멘이 최고였다")
        self.put("바꿨다")
        self.assertEqual(TripSummary.objects.filter(trip=self.trip).count(), 1)  # 여행당 하나
        self.assertEqual(self.put("   ").data["memo"], "")
        self.assertEqual(self.client.get(self.summary_url()).data["memo"], "")

    def test_length_limit_is_300(self):
        self.assertEqual(self.put("가" * 300).status_code, status.HTTP_200_OK)
        self.assertEqual(self.put("가" * 301).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TripSummary.objects.get(trip=self.trip).memo, "가" * 300)  # 거절되면 이전 내용 그대로

    def test_invalid_body(self):
        for body in ({}, {"memo": None}, {"memo": ["a"]}):
            self.assertEqual(self.client.put(self.summary_url(), body, format="json").status_code, status.HTTP_400_BAD_REQUEST, body)

    def test_each_trip_has_its_own_memo(self):
        other = make_trip(self.owner, -2, 0)
        self.put("이 여행")
        self.assertEqual(self.client.get(self.summary_url(other)).data["memo"], "")


class PhotoUploadTests(SummaryTestBase):
    def test_upload_up_to_three_and_keep_order(self):
        ids = [self.upload(image_file(f"{i}.png", size=(100 + i, 100))).data["id"] for i in range(3)]
        data = self.client.get(self.summary_url()).data
        self.assertEqual([p["id"] for p in data["photos"]], ids)
        self.assertEqual([p["order"] for p in data["photos"]], [0, 1, 2])
        self.assertEqual([p["width"] for p in data["photos"]], [100, 101, 102])
        self.assertEqual(len(self.stored_files()), 3)

    def test_fourth_photo_is_rejected(self):
        for _ in range(3):
            self.upload()
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("3장", response.data["detail"])
        self.assertEqual((TripPhoto.objects.count(), len(self.stored_files())), (3, 3))

    def test_stored_as_resized_jpeg_without_exif(self):
        response = self.upload(image_file("big.png", size=(3200, 1600), fmt="PNG"))
        self.assertEqual((response.data["width"], response.data["height"]), (1600, 800))  # 비율을 유지해 줄임
        photo = TripPhoto.objects.get()
        with photo.image.open("rb") as stored:
            image = Image.open(stored)
            self.assertEqual((image.format, image.size), ("JPEG", (1600, 800)))
        self.assertEqual(response.data["size_bytes"], photo.image.size)
        small = self.upload(image_file("small.png", size=(300, 200)))
        self.assertEqual((small.data["width"], small.data["height"]), (300, 200))  # 작은 사진은 키우지 않는다.

    def test_exif_rotation_is_applied_and_exif_removed(self):
        response = self.upload(image_file("rot.jpg", size=(400, 200), fmt="JPEG", exif_orientation=6))  # 90도 회전
        self.assertEqual((response.data["width"], response.data["height"]), (200, 400))
        with TripPhoto.objects.get().image.open("rb") as stored:
            self.assertEqual(len(Image.open(stored).getexif()), 0)

    def test_allowed_formats(self):
        for name, fmt in (("a.jpg", "JPEG"), ("a.png", "PNG"), ("a.webp", "WEBP"), ("a.gif", "GIF")):
            TripPhoto.objects.all().delete()
            self.assertEqual(self.upload(image_file(name, fmt=fmt)).status_code, status.HTTP_201_CREATED, fmt)

    def test_rejects_non_images_and_unsupported_formats(self):
        text = SimpleUploadedFile("note.png", b"not an image", content_type="image/png")
        self.assertEqual(self.upload(text).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.upload(image_file("a.bmp", fmt="BMP")).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.upload(image_file("a.tiff", fmt="TIFF")).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(self.photos_url(), {}, format="multipart").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual((TripPhoto.objects.count(), self.stored_files()), (0, []))

    def test_rejects_files_over_5mb(self):
        big = SimpleUploadedFile("big.jpg", b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 1), content_type="image/jpeg")
        response = self.upload(big)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("5MB", response.data["image"][0])

    def test_file_name_is_not_taken_from_the_upload(self):
        self.upload(image_file("../../etc/passwd.png"))
        (path,) = self.stored_files()
        self.assertTrue(path.startswith(os.path.abspath(self.root)))
        self.assertRegex(os.path.basename(path), r"^[0-9a-f]{32}\.jpg$")
        self.assertIn(f"trips{os.sep}{self.trip.id}{os.sep}", path)


class ReplaceDeleteTests(SummaryTestBase):
    def test_replace_keeps_slot_and_removes_old_file(self):
        first, second = (self.upload(image_file(f"{i}.png", size=(100, 100))).data["id"] for i in range(2))
        old_files = self.stored_files()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.put(self.photo_url(first), {"image": image_file("new.png", size=(640, 480))}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.data["id"], response.data["order"], response.data["width"]), (first, 0, 640))
        data = self.client.get(self.summary_url()).data["photos"]
        self.assertEqual([p["id"] for p in data], [first, second])  # 자리 유지
        new_files = self.stored_files()
        self.assertEqual(len(new_files), 2)
        self.assertEqual(len(set(old_files) - set(new_files)), 1)  # 이전 파일 하나가 지워졌다.

    def test_failed_replace_keeps_the_old_photo(self):
        photo_id = self.upload().data["id"]
        before = self.stored_files()
        bad = self.client.put(self.photo_url(photo_id), {"image": SimpleUploadedFile("x.png", b"nope", content_type="image/png")}, format="multipart")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.stored_files(), before)

    def test_delete_closes_the_gap_and_new_upload_goes_last(self):
        ids = [self.upload().data["id"] for _ in range(3)]
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(self.photo_url(ids[1])).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(self.stored_files()), 2)
        photos = self.client.get(self.summary_url()).data["photos"]
        self.assertEqual([(p["id"], p["order"]) for p in photos], [(ids[0], 0), (ids[2], 1)])
        new_id = self.upload().data["id"]
        self.assertEqual([p["id"] for p in self.client.get(self.summary_url()).data["photos"]], [ids[0], ids[2], new_id])

    def test_deleting_the_trip_removes_photo_files(self):
        self.upload()
        other = make_trip(self.owner, -1, 1)
        self.upload(trip=other)
        self.assertEqual(len(self.stored_files()), 2)
        with self.captureOnCommitCallbacks(execute=True):
            self.trip.delete()
        self.assertEqual(len(self.stored_files()), 1)  # 다른 여행의 사진은 그대로
        self.assertEqual(TripPhoto.objects.filter(trip=other).count(), 1)

    def test_photo_of_another_trip_cannot_be_touched_through_this_trip(self):
        other = make_trip(self.owner, -1, 1)
        photo_id = self.upload(trip=other).data["id"]
        self.assertEqual(self.client.delete(self.photo_url(photo_id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.put(self.photo_url(photo_id), {"image": image_file()}, format="multipart").status_code, 404)
        self.assertTrue(TripPhoto.objects.filter(pk=photo_id).exists())


class PhotoFileAccessTests(SummaryTestBase):
    def setUp(self):
        super().setUp()
        self.photo_id = self.upload(image_file(size=(320, 240))).data["id"]
        self.file_url = f"/api/v1/trip-photos/{self.photo_id}/file/"

    def test_participants_get_the_file(self):
        for user in (self.owner, self.guest):
            self.client.force_authenticate(user)
            response = self.client.get(self.file_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response["Content-Type"], "image/jpeg")
            self.assertIn("private", response["Cache-Control"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertEqual(Image.open(BytesIO(b"".join(response.streaming_content))).size, (320, 240))

    def test_others_and_anonymous_cannot(self):
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.file_url).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.file_url).status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_member_who_left_loses_access(self):
        TripMember.objects.filter(trip=self.trip, user=self.guest).delete()
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.get(self.file_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_file_has_no_public_url(self):
        photo = TripPhoto.objects.get()
        with self.assertRaises(ValueError):
            photo.image.url  # noqa: B018  공개 주소가 없다.
        self.assertFalse(os.path.abspath(photo.image.path).startswith(os.path.abspath(tempfile.gettempdir() + os.sep + "media")))
        response = self.client.get(f"/media/{photo.image.name}")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)  # /media/로는 받을 수 없다.

    def test_missing_file_is_404(self):
        photo = TripPhoto.objects.get()
        os.remove(photo.image.path)
        self.assertEqual(self.client.get(self.file_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_url_in_summary_points_to_the_file_api(self):
        photo = self.client.get(self.summary_url()).data["photos"][0]
        self.assertTrue(photo["url"].startswith(f"/trip-photos/{self.photo_id}/file/?v="))
        self.assertNotIn("trips/", photo["url"])  # 저장 경로를 알려 주지 않는다.


class SummaryAccessTests(SummaryTestBase):
    def test_member_shares_the_summary(self):
        self.client.put(self.summary_url(), {"memo": "같이 쓴 메모"}, format="json")
        photo_id = self.upload().data["id"]
        self.client.force_authenticate(self.guest)
        data = self.client.get(self.summary_url()).data
        self.assertEqual((data["memo"], [p["id"] for p in data["photos"]]), ("같이 쓴 메모", [photo_id]))
        self.assertEqual(self.client.put(self.summary_url(), {"memo": "일행이 고침"}, format="json").status_code, 200)
        self.assertEqual(self.upload().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.delete(self.photo_url(photo_id)).status_code, status.HTTP_204_NO_CONTENT)

    def test_stranger_cannot_read_or_write_anything(self):
        photo_id = self.upload().data["id"]
        self.client.put(self.summary_url(), {"memo": "비밀"}, format="json")
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(self.summary_url()).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.put(self.summary_url(), {"memo": "침입"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.upload().status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.put(self.photo_url(photo_id), {"image": image_file()}, format="multipart").status_code, 404)
        self.assertEqual(self.client.delete(self.photo_url(photo_id)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(TripSummary.objects.get(trip=self.trip).memo, "비밀")
        self.assertEqual(TripPhoto.objects.count(), 1)

    def test_anonymous_is_rejected(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.summary_url()).status_code, (401, 403))
        self.assertIn(self.client.put(self.summary_url(), {"memo": "x"}, format="json").status_code, (401, 403))

    def test_existing_schedule_stays_editable_during_and_after_the_trip(self):
        """여행 중·종료 후에도 기존 일정(경로 카드) 수정이 막히지 않는다."""
        from .models import ItineraryItem

        for start, end in ((-1, 1), (-10, -5)):
            trip = make_trip(self.owner, start, end)
            day = trip.start_date.isoformat()
            created = self.client.post(
                f"/api/v1/trips/{trip.id}/itinerary/init/", {"cards": []}, format="json"
            )
            self.assertIn(created.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST))
            item = ItineraryItem.objects.create(trip=trip, day=day, order=0, kind="sight", title="센소지")
            edited = self.client.patch(f"/api/v1/itinerary-items/{item.id}/", {"time": "10:30"}, format="json")
            self.assertEqual(edited.status_code, status.HTTP_200_OK, (start, end))
            self.assertEqual(self.client.delete(f"/api/v1/itinerary-items/{item.id}/").status_code, status.HTTP_204_NO_CONTENT)
