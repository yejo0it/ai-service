"""
예약 정보로 여행 만들기(2단계).

1단계(analyze → validate)에서 사용자가 확인·수정한 '검증된 예약 정보 객체'로 여행을 만든다.
- 항공권은 필수, 숙소는 선택. 받은 예약 정보는 1단계와 같은 규칙(validate.build_result)으로 서버가 다시 검증한다.
- 여행·비행 구간·숙소를 한 트랜잭션에서 만든다(부분 저장 없음). 같은 요청 번호로 다시 오면 처음 만든 여행을 돌려준다.
- 비행 구간은 FlightSegment로 저장하고, 기존 화면·AI 기능을 위해 Trip.flight_info에 요약(첫 가는 편·마지막 오는 편)을 함께 저장한다.
- 경로 카드는 만들지 않는다: 기존 여행처럼 상세 화면을 처음 열 때 항공·숙소 카드가 만들어진다(관광 일정은 만들지 않는다).
- AI·외부 API를 부르지 않는다. 숙소 위치는 화면에서 사용자가 기존 숙소 검색으로 고른 값만 받는다.
"""

from datetime import date, datetime, time

from django.db import IntegrityError, transaction
from rest_framework import serializers

from ..models import FlightSegment, Trip
from ..serializers import DestinationSerializer, TripSerializer
from . import validate
from .schemas import FLIGHT, HOTEL

class ReservationTripError(Exception):
    """사용자에게 보여 줄 수 있는 생성 오류. detail은 DRF 오류 형식(사전)이다."""

    def __init__(self, detail):
        super().__init__(str(detail))
        self.detail = detail


class HotelPlaceSerializer(serializers.Serializer):
    """숙소 위치: 사용자가 기존 숙소 검색(Google Places)으로 고른 값. 고르지 않았으면 보내지 않는다."""

    place_id = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    latitude = serializers.FloatField(min_value=-90, max_value=90, required=False, allow_null=True, default=None)
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=False, allow_null=True, default=None)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class TripFromReservationSerializer(serializers.Serializer):
    request_id = serializers.RegexField(r"^[A-Za-z0-9-]{8,64}$")
    flight = serializers.DictField()
    hotels = serializers.DictField(required=False, allow_null=True, default=None)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    destinations = DestinationSerializer(many=True, allow_empty=False, max_length=20)
    # 숙소별(hotels.stays와 같은 순서) 위치와 여행지. 없거나 짧으면 나머지는 위치 없이 저장한다.
    hotel_places = serializers.ListField(child=HotelPlaceSerializer(allow_null=True), required=False, default=list, max_length=10)
    hotel_cities = serializers.ListField(
        child=serializers.CharField(max_length=32, allow_blank=True), required=False, default=list, max_length=10
    )

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "종료일은 시작일 이후여야 합니다."})
        return attrs


def _checked(kind, raw, label):
    """1단계와 같은 규칙으로 다시 검증한다. 오류가 있으면 화면과 같은 경로의 오류 목록으로 거절한다."""
    try:
        result = validate.build_result(kind, raw)
    except validate.ReservationDataError as exc:
        raise ReservationTripError({label: [str(exc)]}) from exc
    if not result["valid"]:
        raise ReservationTripError({label: result["errors"]})
    return result["document"]


def _moment(day, clock):
    return datetime.combine(date.fromisoformat(day), time.fromisoformat(clock or "00:00"))


def flatten_segments(document):
    """예약 건별 구간을 여행 순서대로 펼치고 가는 편·오는 편을 정한다."""
    segments = [dict(segment) for itinerary in document["itineraries"] for segment in itinerary["segments"]]
    statuses = [itinerary.get("status") or "" for itinerary in document["itineraries"] for _ in itinerary["segments"]]
    for segment, status in zip(segments, statuses):
        segment["status"] = status
    segments.sort(key=lambda s: _moment(s["departure_date"], s["departure_time"]))

    if not any(segment.get("direction") for segment in segments):
        # 방향을 모르면: 마지막 도착 공항이 첫 출발 공항과 같으면(왕복) 가장 오래 머문 곳(구간 사이 간격이 가장 큰 곳)
        # 뒤를 오는 편으로 본다. 아니면 모두 가는 편(편도·다구간).
        split = None
        if len(segments) > 1 and segments[-1]["arrival_airport_code"] == segments[0]["departure_airport_code"]:
            gaps = []
            for index in range(1, len(segments)):
                previous = segments[index - 1]
                landed = _moment(previous["arrival_date"] or previous["departure_date"], previous["arrival_time"] or previous["departure_time"])
                gaps.append((_moment(segments[index]["departure_date"], segments[index]["departure_time"]) - landed, index))
            split = max(gaps)[1]
        for index, segment in enumerate(segments):
            segment["direction"] = "return" if split is not None and index >= split else "outbound"
    else:
        for segment in segments:
            segment["direction"] = segment.get("direction") or "outbound"
    return segments


def _stamp(day, clock):
    return f"{day}T{clock}:00" if day and clock else None


def _airport(code, name):
    return {"code": code, "name": (name or code)[:60]}


def flight_summary(segments):
    """기존 화면·AI 기능이 읽는 Trip.flight_info(가는 편 1개 + 오는 편 1개) 요약."""
    outbound = [s for s in segments if s["direction"] == "outbound"] or segments
    returning = [s for s in segments if s["direction"] == "return" and s not in outbound]
    first, last = outbound[0], outbound[-1]
    info = {
        "airline": first["airline_name"] or "",
        "flight_number": first["flight_number"],
        "departure_at": _stamp(first["departure_date"], first["departure_time"]),
        "arrival_at": _stamp(last["arrival_date"], last["arrival_time"]),
        "departure_airport": _airport(first["departure_airport_code"], first["departure_airport_name"]),
        "arrival_airport": _airport(last["arrival_airport_code"], last["arrival_airport_name"]),
    }
    if returning:
        back_first, back_last = returning[0], returning[-1]
        info.update(
            {
                "return_airline": back_first["airline_name"] or "",
                "return_flight_number": back_first["flight_number"],
                "return_departure_at": _stamp(back_first["departure_date"], back_first["departure_time"]),
                "return_arrival_at": _stamp(back_last["arrival_date"], back_last["arrival_time"]),
                "return_departure_airport": _airport(back_first["departure_airport_code"], back_first["departure_airport_name"]),
                "return_arrival_airport": _airport(back_last["arrival_airport_code"], back_last["arrival_airport_name"]),
            }
        )
    if len(segments) > 2 or len(outbound) > 1 or len(returning) > 1:
        info["note"] = "예약 확인서로 등록한 항공편(경유·다구간 포함). 구간별 정보는 비행 구간에서 확인하세요."
    return {key: value for key, value in info.items() if value is not None}


def _hotel_payload(stay, place, city_code):
    place = place or {}
    return {
        "name": stay["name"],
        "address": (place.get("address") or stay["address"] or "")[:255],
        "place_id": place.get("place_id") or "",
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "phone": place.get("phone") or "",
        "city_code": city_code or "",
        "check_in": stay["check_in_date"],
        "check_out": stay["check_out_date"],
        "check_in_time": stay["check_in_time"],
        "check_out_time": stay["check_out_time"],
    }


def create_trip(user, data, request=None):
    """
    검증된 요청(TripFromReservationSerializer) -> (Trip, created). 같은 요청 번호면 (기존 여행, False).
    검증에 실패하면 ReservationTripError. 모든 저장은 한 트랜잭션이라 실패하면 아무것도 남지 않는다.
    """
    existing = Trip.objects.filter(owner=user, creation_key=data["request_id"]).first()
    if existing:
        return existing, False

    flight = _checked(FLIGHT, data["flight"], "flight")
    segments = flatten_segments(flight)
    if not segments:
        raise ReservationTripError({"flight": ["항공편 구간을 한 개 이상 입력해 주세요."]})
    stays = _checked(HOTEL, data["hotels"], "hotels")["stays"] if data.get("hotels") else []

    start, end = data["start_date"], data["end_date"]
    outside = [s["flight_number"] for s in segments if not start <= date.fromisoformat(s["departure_date"]) <= end]
    if outside:
        raise ReservationTripError({"start_date": [f"여행 기간 밖에 출발하는 항공편이 있어요: {', '.join(outside)}"]})

    places, cities = data.get("hotel_places") or [], data.get("hotel_cities") or []
    payload = {
        "destinations": [dict(entry) for entry in data["destinations"]],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "flight_info": flight_summary(segments),
        "hotels": [
            _hotel_payload(stay, places[index] if index < len(places) else None, cities[index] if index < len(cities) else "")
            for index, stay in enumerate(stays)
        ],
    }
    serializer = TripSerializer(data=payload, context={"request": request})
    if not serializer.is_valid():
        raise ReservationTripError(serializer.errors)

    try:
        with transaction.atomic():
            trip = serializer.save(owner=user)
            trip.creation_key = data["request_id"]
            trip.save(update_fields=["creation_key"])
            FlightSegment.objects.bulk_create(
                FlightSegment(
                    trip=trip,
                    order=order,
                    direction=segment["direction"],
                    airline_name=segment["airline_name"] or "",
                    flight_number=segment["flight_number"],
                    departure_airport_code=segment["departure_airport_code"],
                    departure_airport_name=segment["departure_airport_name"] or "",
                    arrival_airport_code=segment["arrival_airport_code"],
                    arrival_airport_name=segment["arrival_airport_name"] or "",
                    departure_date=segment["departure_date"],
                    departure_time=segment["departure_time"],
                    arrival_date=segment["arrival_date"],
                    arrival_time=segment["arrival_time"],
                    status=segment["status"][:40],
                )
                for order, segment in enumerate(segments)
            )
    except IntegrityError:
        # 같은 요청이 동시에 두 번 온 경우: 먼저 만든 여행을 돌려준다.
        existing = Trip.objects.filter(owner=user, creation_key=data["request_id"]).first()
        if existing is None:  # 다른 사람이 쓴 요청 번호와 겹친 경우(사실상 없음): 새 번호로 다시 보내게 한다.
            raise ReservationTripError({"request_id": ["요청 번호가 겹쳤어요. 다시 시도해 주세요."]}) from None
        return existing, False
    return trip, True
