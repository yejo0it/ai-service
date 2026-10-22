"""
여행 요약: 여행 시작일부터 작성하는 한 줄 메모와 사진(최대 3장).

- GET  /trips/{id}/summary/                  메모와 사진 목록(순서대로)
- PUT  /trips/{id}/summary/                  한 줄 메모 저장(최대 300자, 비우면 지운다)
- POST /trips/{id}/photos/                   사진 추가(multipart `image`, 여행당 최대 3장)
- PUT  /trips/{id}/photos/{photo_id}/        사진 교체(같은 자리·순서 유지)
- DELETE /trips/{id}/photos/{photo_id}/      사진 삭제(남은 사진 순서는 앞으로 당긴다)
- GET  /trip-photos/{photo_id}/file/         사진 파일(로그인한 여행 참여자만)
만든 회원과 일행이 같은 요약을 보고 고치며, 그 밖의 회원에게는 여행이 없는 것(404)이다.
쓰기는 여행 시작일(서버 시간 Asia/Seoul)부터 할 수 있다. 사진은 공개 주소가 없고 위 파일 API로만 받는다.
"""

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Trip, TripPhoto, TripSummary
from .photos import PhotoError, make_trip_photo


def accessible_trip(request, pk):
    return get_object_or_404(Trip.objects.accessible_to(request.user), pk=pk)


def is_writable(trip):
    """여행 시작일이 되면(여행 중·종료 후) 요약을 쓸 수 있다."""
    return timezone.localdate() >= trip.start_date


def not_started_response():
    return Response({"detail": "여행이 시작되면 작성할 수 있어요."}, status=status.HTTP_403_FORBIDDEN)


def photo_data(photo):
    return {
        "id": photo.id,
        "order": photo.order,
        "width": photo.width,
        "height": photo.height,
        "size_bytes": photo.size_bytes,
        # 파일 API 주소(API 주소 기준). 사진을 바꾸면 v가 달라져 브라우저가 새 파일을 받는다.
        "url": f"/trip-photos/{photo.id}/file/?v={int(photo.updated_at.timestamp())}",
    }


def summary_data(trip):
    summary = TripSummary.objects.filter(trip=trip).first()
    return {
        "memo": summary.memo if summary else "",
        "photos": [photo_data(photo) for photo in trip.photos.all()],
        "max_photos": TripPhoto.MAX_PER_TRIP,
        "writable": is_writable(trip),
    }


class MemoSerializer(serializers.Serializer):
    memo = serializers.CharField(max_length=TripSummary.MEMO_MAX, allow_blank=True, trim_whitespace=True)


class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(summary_data(accessible_trip(request, pk)))

    def put(self, request, pk):
        trip = accessible_trip(request, pk)
        if not is_writable(trip):
            return not_started_response()
        serializer = MemoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        TripSummary.objects.update_or_create(trip=trip, defaults={"memo": serializer.validated_data["memo"]})
        return Response(summary_data(trip))


def read_upload(request):
    """요청의 사진 파일을 여행 사진으로 만든다. 쓸 수 없으면 (None, 오류 응답)."""
    upload = request.FILES.get("image")
    if upload is None:
        return None, Response({"image": ["사진 파일을 선택해 주세요."]}, status=status.HTTP_400_BAD_REQUEST)
    try:
        return make_trip_photo(upload), None
    except PhotoError as exc:
        return None, Response({"image": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)


class PhotoListView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        trip = accessible_trip(request, pk)
        if not is_writable(trip):
            return not_started_response()
        processed, error = read_upload(request)
        if error:
            return error
        content, width, height = processed
        with transaction.atomic():
            # 동시에 올려도 3장을 넘지 않도록 여행 행을 잠근다.
            Trip.objects.select_for_update().get(pk=trip.pk)
            photos = list(trip.photos.all())
            if len(photos) >= TripPhoto.MAX_PER_TRIP:
                return Response(
                    {"detail": f"사진은 {TripPhoto.MAX_PER_TRIP}장까지 올릴 수 있어요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            photo = TripPhoto(trip=trip, order=len(photos), width=width, height=height, size_bytes=content.size)
            photo.image.save(content.name, content, save=False)
            photo.save()
        return Response(photo_data(photo), status=status.HTTP_201_CREATED)


class PhotoView(APIView):
    permission_classes = [IsAuthenticated]

    def get_photo(self, request, pk, photo_id):
        trip = accessible_trip(request, pk)
        return trip, get_object_or_404(TripPhoto, pk=photo_id, trip=trip)

    def put(self, request, pk, photo_id):
        trip, photo = self.get_photo(request, pk, photo_id)
        if not is_writable(trip):
            return not_started_response()
        processed, error = read_upload(request)
        if error:
            return error
        content, width, height = processed
        old_name = photo.image.name
        photo.image.save(content.name, content, save=False)
        photo.width, photo.height, photo.size_bytes = width, height, content.size
        photo.save()  # 순서(order)는 그대로 둔다.
        transaction.on_commit(lambda: photo.image.storage.delete(old_name))
        return Response(photo_data(photo))

    @transaction.atomic
    def delete(self, request, pk, photo_id):
        trip, photo = self.get_photo(request, pk, photo_id)
        if not is_writable(trip):
            return not_started_response()
        photo.delete()  # 파일은 커밋된 뒤 지운다(trips.models의 신호).
        for order, other in enumerate(trip.photos.all()):  # 남은 사진을 앞에서부터 채운다.
            if other.order != order:
                TripPhoto.objects.filter(pk=other.pk).update(order=order)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PhotoFileView(APIView):
    """`GET /trip-photos/{id}/file/` — 로그인한 여행 참여자만 받을 수 있는 사진 파일."""

    permission_classes = [IsAuthenticated]

    def get(self, request, photo_id):
        photo = get_object_or_404(
            TripPhoto, pk=photo_id, trip__in=Trip.objects.accessible_to(request.user)
        )
        try:
            file = photo.image.open("rb")
        except (FileNotFoundError, ValueError) as exc:
            raise Http404 from exc
        response = FileResponse(file, content_type="image/jpeg")
        response["Cache-Control"] = "private, max-age=86400"  # 공유 캐시에는 남기지 않는다.
        response["X-Content-Type-Options"] = "nosniff"
        return response
