"""
예약 확인서 분석 API (1단계).

- POST /api/v1/reservations/analyze/   multipart(file, type=flight|hotel) -> 추출·정규화·검증한 예약 정보
- POST /api/v1/reservations/validate/  사용자가 고친 예약 정보를 같은 방식으로 검증(모델 호출 없음)
둘 다 검증된 '예약 정보 객체'를 같은 모양({kind, document, valid, errors, warnings})으로 돌려준다.
여행·항공편·숙소에는 아무것도 저장하지 않고, 업로드 파일도 저장하지 않는다. 문서 내용·파일 이름은 기록하지 않는다.
운영에서는 RESERVATION_ANALYSIS_ENABLED=1일 때만 열린다(꺼져 있으면 404).
"""

import logging

from django.conf import settings
from django.http import Http404
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from . import extract, files, validate
from . import trips as reservation_trips
from . import attach
from .schemas import KINDS

logger = logging.getLogger(__name__)

THROTTLE_MESSAGES = {
    "reservation_hour": "예약 확인서 분석 요청이 너무 많아요. 잠시 후 다시 시도해 주세요. (시간당 10회)",
    "reservation_day": "오늘 예약 확인서 분석 한도(30회)를 모두 썼어요. 내일 다시 시도하거나 직접 입력해 주세요.",
}


class _Throttle(UserRateThrottle):
    """
    분석 요청 제한(사용자별). 모든 제한을 통과했을 때만 한 번으로 센다
    (한 제한에 걸려 거절된 요청이 다른 제한의 횟수를 쓰지 않게).
    """

    def throttle_success(self):
        return True

    def record(self):
        self.history.insert(0, self.now)
        self.cache.set(self.key, self.history, self.duration)


class HourThrottle(_Throttle):
    scope = "reservation_hour"


class DayThrottle(_Throttle):
    scope = "reservation_day"


def check_limits(request, view):
    """
    모델을 부르기 직전에 확인한다(파일 검증에서 거절된 요청은 세지 않는다). 넘으면 429 응답, 아니면 None(이번 요청을 센다).
    """
    throttles = [HourThrottle(), DayThrottle()]
    denied = [throttle for throttle in throttles if not throttle.allow_request(request, view)]
    if denied:
        wait = max(int(throttle.wait() or 0) for throttle in denied)
        scope = "reservation_day" if any(t.scope == "reservation_day" for t in denied) else "reservation_hour"
        return Response(
            {"detail": THROTTLE_MESSAGES[scope]},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(max(wait, 1))},
        )
    for throttle in throttles:
        throttle.record()
    return None


class ReservationView(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        if not getattr(settings, "RESERVATION_ANALYSIS_ENABLED", False):
            raise Http404
        super().initial(request, *args, **kwargs)


class AnalyzeView(ReservationView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        kind = request.data.get("type")
        upload = request.FILES.get("file")
        if kind not in KINDS:
            return Response({"detail": "예약 종류(항공권·숙소)를 선택해 주세요."}, status=status.HTTP_400_BAD_REQUEST)
        if upload is None:
            return Response({"detail": "파일을 선택해 주세요."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            prepared = files.prepare(upload)
        except files.ReservationFileError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        limited = check_limits(request, self)
        if limited:
            return limited

        try:
            parsed = extract.extract(kind, prepared)
            result = validate.build_result(kind, parsed.model_dump())
        except extract.ReservationAiError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)

        logger.info("reservation analyzed kind=%s method=%s pages=%d valid=%s", kind, prepared.method, prepared.pages, result["valid"])
        return Response({**result, "method": prepared.method, "pages": prepared.pages})


class ValidateView(ReservationView):
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "reservation_validate"

    def post(self, request):
        kind = request.data.get("type")
        if kind not in KINDS:
            return Response({"detail": "예약 종류(항공권·숙소)가 올바르지 않아요."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(validate.build_result(kind, request.data.get("document")))
        except validate.ReservationDataError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class TripFromReservationView(ReservationView):
    """
    `POST /api/v1/trips/from-reservations/` — 확인한 예약 정보(항공권 필수·숙소 선택)로 여행을 만든다(2단계).
    여행·비행 구간·숙소를 한 번에 저장하고(부분 저장 없음), 같은 request_id로 다시 오면 처음 만든 여행을 200으로 돌려준다.
    AI·외부 API를 부르지 않는다.
    """

    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "reservation_validate"

    def post(self, request):
        serializer = reservation_trips.TripFromReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            trip, created = reservation_trips.create_trip(request.user, serializer.validated_data, request)
        except reservation_trips.ReservationTripError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        from ..serializers import TripSerializer

        trip = type(trip).objects.prefetch_related("hotels", "flight_segments").get(pk=trip.pk)
        data = TripSerializer(trip, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReservationConfigView(APIView):
    """`GET /api/v1/reservations/config/` — 예약 확인서 기능을 쓸 수 있는지(화면이 '예약 정보로 만들기'를 보일지 정한다)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"enabled": bool(getattr(settings, "RESERVATION_ANALYSIS_ENABLED", False))})


def _trip_for(request, pk):
    from django.shortcuts import get_object_or_404

    from ..models import Trip

    return get_object_or_404(Trip.objects.accessible_to(request.user), pk=pk)


def _trip_and_itinerary(request, trip):
    from ..itinerary_views import itinerary_response
    from ..models import Trip
    from ..serializers import TripSerializer

    trip = Trip.objects.prefetch_related("hotels", "flight_segments").get(pk=trip.pk)
    response = itinerary_response(trip)
    response.data["trip"] = TripSerializer(trip, context={"request": request}).data
    return response


class TripReservationPreviewView(ReservationView):
    """
    `POST /api/v1/trips/{id}/reservations/preview/` — 기존 여행에 예약 정보를 넣으면 무엇이 바뀌는지(저장하지 않음):
    새 구간·숙소, 이미 있는 예약, 숙소 겹침, 여행 기간 변경, 함께 빠지는 자동 카드, 시간이 겹치는 기존 일정.
    """

    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "reservation_validate"

    def post(self, request, pk):
        trip = _trip_for(request, pk)
        serializer = attach.AttachSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = attach.plan(trip, serializer.validated_data)
        except reservation_trips.ReservationTripError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(attach.as_response(trip, result))


class ApplySerializer(attach.AttachSerializer):
    # 예약이 여행 기간 밖이면 기간을 늘리는 데 동의해야 저장한다.
    extend_dates = serializers.BooleanField(required=False, default=False)
    # False: 예약 정보만 저장(경로에 더하지 않음). True: 고른 카드를 경로에 넣고 고른 충돌 일정을 지운다.
    reflect = serializers.BooleanField(required=False, default=False)
    cards = serializers.ListField(child=serializers.DictField(), required=False, default=list, max_length=attach.MAX_CARDS)
    remove_item_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=attach.MAX_CARDS
    )

    def validate_cards(self, value):
        from ..itinerary_views import CardSerializer

        serializer = CardSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class TripReservationApplyView(ReservationView):
    """
    `POST /api/v1/trips/{id}/reservations/apply/` — 예약 정보를 저장하고 승인한 변경만 경로에 반영한다(한 트랜잭션).
    바뀐 여행과 일정을 돌려준다. 같은 예약을 다시 보내면 중복으로 건너뛴다.
    """

    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "reservation_validate"

    def post(self, request, pk):
        trip = _trip_for(request, pk)
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            trip, _ = attach.apply(
                trip, data, data["cards"], data["remove_item_ids"], data["extend_dates"], data["reflect"]
            )
        except reservation_trips.ReservationTripError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return _trip_and_itinerary(request, trip)


class FlightSegmentView(APIView):
    """`DELETE /api/v1/trips/{id}/flight-segments/{order}/` — 예약 항공 구간 하나와 그 자동 카드를 지운다(화면에서 확인 후)."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, order):
        trip = attach.delete_segment(_trip_for(request, pk), order)
        if trip is None:
            return Response({"detail": "항공 구간을 찾을 수 없어요."}, status=status.HTTP_404_NOT_FOUND)
        return _trip_and_itinerary(request, trip)
