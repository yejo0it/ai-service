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
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from . import extract, files, validate
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
