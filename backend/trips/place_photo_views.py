"""
`GET /api/v1/places/photo/?place_id=...` — 여행 경로 장소의 대표 사진 주소와 작성자(trips.place_photos).

- 로그인한 사용자만, 그리고 자기가 볼 수 있는 여행의 일정에 있는 장소(항공편 제외)의 place_id만 받는다.
  (아무 place_id나 조회해 서버 Google 키로 사진을 받아 가는 것을 막는다.)
- 사진이 없거나 월 상한을 넘었거나 Google 오류여도 200으로 `photo_uri: null`을 돌려줘 일정 표시에 영향이 없다.
- 응답은 브라우저가 1시간 동안만 재사용한다(오류는 저장하지 않는다).
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import place_photos
from .models import ItineraryItem, Trip

BROWSER_CACHE_SECONDS = 60 * 60


class PlacePhotoView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "place_photo"

    def get(self, request):
        place_id = request.query_params.get("place_id", "").strip()
        if not place_photos.PLACE_ID_PATTERN.match(place_id):
            return Response({"detail": "장소 번호가 올바르지 않아요."}, status=status.HTTP_400_BAD_REQUEST)
        in_my_trips = (
            ItineraryItem.objects.filter(place_id=place_id, trip__in=Trip.objects.accessible_to(request.user))
            .exclude(kind=ItineraryItem.Kind.FLIGHT)
            .exists()
        )
        if not in_my_trips:
            return Response({"detail": "장소를 찾을 수 없어요."}, status=status.HTTP_404_NOT_FOUND)

        data = place_photos.lookup(place_id)
        response = Response(data)
        response["Cache-Control"] = (
            "no-store" if data["status"] == place_photos.ERROR else f"private, max-age={BROWSER_CACHE_SECONDS}"
        )
        return response
