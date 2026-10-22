"""
기존 여행에 예약 확인서 추가(3단계).

1단계에서 확인한 예약 정보(항공권·숙소, 각각 선택)를 이미 있는 여행에 저장한다. 사용자가 만든 일정은 보존하는 것이 원칙이다.
- preview: 저장하지 않고 무엇이 바뀌는지 계산한다(새 구간·숙소, 이미 있는 예약, 숙소 겹침, 여행 기간 변경, 시간이 겹치는 기존 일정).
- apply: 예약 정보를 저장하고, 사용자가 승인한 변경만 여행 경로에 반영한다. 한 트랜잭션이라 부분 저장이 없다.
  같은 예약을 다시 저장하면 중복으로 보고 건너뛰므로 두 번 저장되지 않는다.

정책
- 항공: 구간이 없는 여행(직접 등록한 flight_info만 있음)에 추가하면 예약 구간으로 교체한다. 구간이 있으면 기본은 추가(같은 편명·출발일은
  건너뜀)이고, 전체 교체를 고를 수 있다. 교체하면 이전 항공 자동 카드는 함께 빠진다(등록 정보와 어긋나지 않게).
- 숙소: 같은 이름·같은 기간이면 이미 있는 예약. 다른 숙소와 묵는 밤이 겹치면 사용자가 '건너뛰기'(기본) 또는 '기존 숙소 교체'를 고른다.
  교체하면 기존 숙소와 그 자동 카드가 함께 빠진다.
- 여행 기간: 예약이 기간 밖이면 사용자가 동의한 경우에만 늘린다(줄이지 않는다).
- 경로 반영: 새 항공·숙소 카드(화면이 만든 카드 중 사용자가 고른 것)와, 시간이 겹치는 기존 일정 중 사용자가 지우기로 고른 것만 반영한다.
  '예약 정보만 저장'이면 경로에는 아무것도 더하지 않는다. 자동으로 기존 일정을 바꾸거나 다시 계산하지 않는다.
- AI·외부 API를 부르지 않는다.
"""

from datetime import date, datetime, time, timedelta

from django.db import transaction
from rest_framework import serializers

from ..cities import normalize_key
from ..models import FlightSegment, Hotel, ItineraryItem, Trip
from . import trips as reservation_trips
from .schemas import FLIGHT, HOTEL

# 항공편이 차지하는 시간: 출발 2시간 전 ~ 도착 1시간 뒤(도착 시각을 모르면 출발 1시간 뒤까지). 그 사이 시각의 기존 일정은 충돌로 안내한다.
BEFORE_DEPARTURE = timedelta(hours=2)
AFTER_ARRIVAL = timedelta(hours=1)
MAX_CARDS = 200


class AttachSerializer(serializers.Serializer):
    flight = serializers.DictField(required=False, allow_null=True, default=None)
    flight_mode = serializers.ChoiceField(choices=["add", "replace"], required=False, default="add")
    hotels = serializers.DictField(required=False, allow_null=True, default=None)
    # 숙소별(hotels.stays와 같은 순서): 기존 숙소와 겹칠 때 skip(건너뛰기) 또는 replace(기존 숙소 교체). 겹치지 않으면 무시한다.
    hotel_decisions = serializers.ListField(
        child=serializers.ChoiceField(choices=["skip", "replace"]), required=False, default=list, max_length=10
    )
    hotel_places = serializers.ListField(
        child=reservation_trips.HotelPlaceSerializer(allow_null=True), required=False, default=list, max_length=10
    )
    hotel_cities = serializers.ListField(
        child=serializers.CharField(max_length=32, allow_blank=True), required=False, default=list, max_length=10
    )

    def validate(self, attrs):
        if not attrs.get("flight") and not attrs.get("hotels"):
            raise serializers.ValidationError({"detail": "추가할 항공권이나 숙소 예약 정보를 보내 주세요."})
        return attrs


def _moment(day, clock):
    return datetime.combine(day if isinstance(day, date) else date.fromisoformat(day), clock if isinstance(clock, time) else time.fromisoformat(clock or "00:00"))


def segment_dict(row):
    """저장된 구간 -> flatten_segments와 같은 모양의 사전"""
    return {
        "airline_name": row.airline_name,
        "flight_number": row.flight_number,
        "departure_airport_code": row.departure_airport_code,
        "departure_airport_name": row.departure_airport_name,
        "arrival_airport_code": row.arrival_airport_code,
        "arrival_airport_name": row.arrival_airport_name,
        "departure_date": row.departure_date.isoformat(),
        "departure_time": row.departure_time.strftime("%H:%M"),
        "arrival_date": row.arrival_date.isoformat() if row.arrival_date else None,
        "arrival_time": row.arrival_time.strftime("%H:%M") if row.arrival_time else None,
        "direction": row.direction,
        "status": row.status,
    }


def _segment_key(segment):
    return (segment["flight_number"], segment["departure_date"])


def _card(item):
    return {"id": item.id, "title": item.title, "day": item.day.isoformat(), "time": item.time.strftime("%H:%M") if item.time else ""}


def _hotel_nights_end(hotel_in, hotel_out):
    return hotel_out or (hotel_in + timedelta(days=1))


def _hotel_cards(trip, hotel):
    """숙소의 자동 카드(체크인·숙박·체크아웃): 같은 이름이고 숙박 기간 안의 날짜"""
    last = hotel.check_out or hotel.check_in
    return list(
        trip.itinerary_items.filter(
            source=ItineraryItem.Source.AUTO, kind=ItineraryItem.Kind.HOTEL, title=hotel.name,
            day__gte=hotel.check_in, day__lte=last,
        ).order_by("day", "order")
    )


def plan(trip, data):
    """
    저장하지 않고 바뀔 내용을 계산한다. 잘못된 예약 정보면 ReservationTripError.
    반환 사전의 날짜는 date 객체이고, 응답에 쓸 때 as_response로 바꾼다.
    """
    result = {"flight": None, "hotels": [], "replaced_cards": [], "conflicts": []}

    # ---------------- 항공
    new_segments = []
    if data.get("flight"):
        document = reservation_trips._checked(FLIGHT, data["flight"], "flight")
        incoming = reservation_trips.flatten_segments(document)
        existing = list(trip.flight_segments.all())
        legacy = bool(trip.flight_info) and not existing
        mode = "replace" if legacy or (existing and data.get("flight_mode") == "replace") else "add"
        keys = set() if mode == "replace" else {_segment_key(segment_dict(row)) for row in existing}
        duplicates = []
        for segment in incoming:
            if _segment_key(segment) in keys:
                duplicates.append(segment)
            else:
                keys.add(_segment_key(segment))
                new_segments.append(segment)
        base = [] if mode == "replace" else [segment_dict(row) for row in existing]
        final = sorted(base + new_segments, key=lambda s: _moment(s["departure_date"], s["departure_time"]))
        result["flight"] = {"mode": mode, "legacy_replaced": legacy, "new": new_segments, "duplicates": duplicates, "final": final}
        if mode == "replace":
            result["replaced_cards"] += list(
                trip.itinerary_items.filter(source=ItineraryItem.Source.AUTO, kind=ItineraryItem.Kind.FLIGHT).order_by("day", "order")
            )

    # ---------------- 숙소
    stays = reservation_trips._checked(HOTEL, data["hotels"], "hotels")["stays"] if data.get("hotels") else []
    decisions = data.get("hotel_decisions") or []
    existing_hotels = list(trip.hotels.all())
    kept_stays = []
    for index, stay in enumerate(stays):
        check_in, check_out = date.fromisoformat(stay["check_in_date"]), date.fromisoformat(stay["check_out_date"])
        duplicate = any(
            hotel.name.strip().lower() == stay["name"].strip().lower() and hotel.check_in == check_in and hotel.check_out == check_out
            for hotel in existing_hotels
        )
        overlaps = [
            hotel for hotel in existing_hotels
            if hotel.check_in < _hotel_nights_end(check_in, check_out) and check_in < _hotel_nights_end(hotel.check_in, hotel.check_out)
        ]
        if duplicate:
            status, overlaps = "duplicate", []
        elif overlaps:
            status = "replace" if index < len(decisions) and decisions[index] == "replace" else "skip"
        else:
            status = "new"
        entry = {"index": index, "stay": stay, "status": status, "overlaps": overlaps, "check_in": check_in, "check_out": check_out}
        result["hotels"].append(entry)
        if status in ("new", "replace"):
            kept_stays.append(entry)
            if status == "replace":
                for hotel in overlaps:
                    result["replaced_cards"] += _hotel_cards(trip, hotel)
    for position, entry in enumerate(kept_stays):  # 새로 넣을 숙소끼리도 묵는 밤이 겹치면 안 된다.
        for other in kept_stays[position + 1:]:
            if entry["check_in"] < other["check_out"] and other["check_in"] < entry["check_out"]:
                raise reservation_trips.ReservationTripError({"hotels": ["새 숙소끼리 숙박 기간이 겹쳐요. 날짜를 확인해 주세요."]})

    # ---------------- 여행 기간
    days = [date.fromisoformat(s["departure_date"]) for s in new_segments]
    for entry in kept_stays:
        days += [entry["check_in"], entry["check_out"]]
    start = min([trip.start_date, *days])
    end = max([trip.end_date, *days])
    result["dates"] = {"start": start, "end": end, "extend": (start, end) != (trip.start_date, trip.end_date),
                       "current_start": trip.start_date, "current_end": trip.end_date}

    # ---------------- 시간이 겹치는 기존 일정(사용자가 만든 일정만, 시각이 있는 것만)
    timed = list(trip.itinerary_items.exclude(source=ItineraryItem.Source.AUTO).exclude(time=None))
    seen = set()
    for segment in new_segments:
        departure = _moment(segment["departure_date"], segment["departure_time"])
        if segment["arrival_date"] and segment["arrival_time"]:
            arrival = _moment(segment["arrival_date"], segment["arrival_time"])
        else:
            arrival = departure
        if arrival < departure:  # 시차로 도착이 더 빨라 보이면 출발 기준으로만 본다.
            arrival = departure
        window = (departure - BEFORE_DEPARTURE, arrival + AFTER_ARRIVAL)
        for item in timed:
            when = _moment(item.day, item.time)
            if window[0] <= when <= window[1] and item.id not in seen:
                seen.add(item.id)
                result["conflicts"].append({"item": item, "reason": f"{segment['flight_number']} 비행 시간과 겹쳐요"})
    return result


def as_response(trip, result):
    """plan 결과 -> 화면에 보낼 JSON"""
    flight = result["flight"]
    return {
        "flight": flight and {
            "mode": flight["mode"],
            "legacy_replaced": flight["legacy_replaced"],
            "new": flight["new"],
            "duplicates": flight["duplicates"],
            "final_count": len(flight["final"]),
        },
        "hotels": [
            {
                "index": entry["index"],
                "status": entry["status"],
                "stay": entry["stay"],
                "overlaps": [
                    {"id": hotel.id, "name": hotel.name, "check_in": hotel.check_in.isoformat(),
                     "check_out": hotel.check_out.isoformat() if hotel.check_out else None}
                    for hotel in entry["overlaps"]
                ],
            }
            for entry in result["hotels"]
        ],
        "dates": {key: (value.isoformat() if isinstance(value, date) else value) for key, value in result["dates"].items()},
        "replaced_cards": [_card(item) for item in result["replaced_cards"]],
        "conflicts": [{**_card(entry["item"]), "reason": entry["reason"]} for entry in result["conflicts"]],
        "itinerary_initialized": trip.itinerary_initialized,
    }


def _save_segments(trip, segments):
    trip.flight_segments.all().delete()
    FlightSegment.objects.bulk_create(
        FlightSegment(
            trip=trip, order=order, direction=segment["direction"], airline_name=segment["airline_name"] or "",
            flight_number=segment["flight_number"], departure_airport_code=segment["departure_airport_code"],
            departure_airport_name=segment["departure_airport_name"] or "", arrival_airport_code=segment["arrival_airport_code"],
            arrival_airport_name=segment["arrival_airport_name"] or "", departure_date=segment["departure_date"],
            departure_time=segment["departure_time"], arrival_date=segment["arrival_date"], arrival_time=segment["arrival_time"],
            status=(segment.get("status") or "")[:40],
        )
        for order, segment in enumerate(segments)
    )
    trip.flight_info = reservation_trips.flight_summary(segments) if segments else None
    trip.date_source = Trip.DateSource.FLIGHT if segments else Trip.DateSource.MANUAL
    trip.save(update_fields=["flight_info", "date_source", "updated_at"])


@transaction.atomic
def apply(trip, data, cards, remove_item_ids, extend_dates, reflect):
    """
    예약 정보를 저장하고 승인한 변경만 경로에 반영한다. 잘못되면 ReservationTripError(아무것도 저장하지 않음).
    cards: 화면이 만든 새 항공·숙소 카드(CardSerializer로 검증된 값) 중 사용자가 고른 것
    remove_item_ids: 시간이 겹치는 기존 일정 중 사용자가 지우기로 고른 것(충돌 목록에 있는 일정만 지운다)
    """
    from ..itinerary_views import clear_expected_arrival, days_map, save_days
    from ..registration import insert_auto_cards

    trip = Trip.objects.select_for_update().get(pk=trip.pk)
    result = plan(trip, data)

    dates = result["dates"]
    if dates["extend"]:
        if not extend_dates:
            raise reservation_trips.ReservationTripError({"dates": ["예약이 여행 기간 밖이에요. 여행 기간을 늘리는 데 동의해 주세요."]})
        trip.start_date, trip.end_date = dates["start"], dates["end"]
        trip.save(update_fields=["start_date", "end_date", "updated_at"])

    # 교체한 항공·숙소의 자동 카드는 등록 정보와 어긋나지 않게 함께 뺀다(미리보기에 표시한 카드).
    replaced_ids = {item.id for item in result["replaced_cards"]}
    changed_days = {item.day for item in result["replaced_cards"]}

    if result["flight"]:
        _save_segments(trip, result["flight"]["final"])

    places, cities = data.get("hotel_places") or [], data.get("hotel_cities") or []
    for entry in result["hotels"]:
        if entry["status"] not in ("new", "replace"):
            continue
        for hotel in entry["overlaps"] if entry["status"] == "replace" else []:
            if hotel.pk:  # 여러 새 숙소가 같은 기존 숙소와 겹치면 한 번만 지운다.
                hotel.delete()
        index = entry["index"]
        payload = reservation_trips._hotel_payload(
            entry["stay"], places[index] if index < len(places) else None, cities[index] if index < len(cities) else ""
        )
        Hotel.objects.create(trip=trip, **{**payload, "city_code": normalize_key(payload["city_code"])[:32]})

    trip.itinerary_items.filter(id__in=replaced_ids).delete()

    if reflect and trip.itinerary_initialized:
        conflict_ids = {entry["item"].id for entry in result["conflicts"]}
        approved = [item_id for item_id in remove_item_ids if item_id in conflict_ids]
        changed_days |= set(trip.itinerary_items.filter(id__in=approved).values_list("day", flat=True))
        trip.itinerary_items.filter(id__in=approved).delete()
        days = days_map(trip)
        new_cards = []
        for card in cards:
            if card.get("kind") not in (ItineraryItem.Kind.FLIGHT, ItineraryItem.Kind.HOTEL) or card.get("day") not in days:
                continue
            new_cards.append({**card, "source": ItineraryItem.Source.AUTO})
            changed_days.add(card["day"])
        insert_auto_cards(days, new_cards)
        save_days(trip, days, ItineraryItem.Source.AUTO)
    clear_expected_arrival(trip, changed_days)
    return trip, result


@transaction.atomic
def delete_segment(trip, order):
    """예약 항공 구간 하나를 지우고 그 구간의 자동 카드도 지운다. 남은 구간으로 flight_info 요약을 다시 만든다."""
    from ..itinerary_views import clear_expected_arrival

    trip = Trip.objects.select_for_update().get(pk=trip.pk)
    rows = list(trip.flight_segments.all())
    target = next((row for row in rows if row.order == order), None)
    if target is None:
        return None
    cards = trip.itinerary_items.filter(
        source=ItineraryItem.Source.AUTO, kind=ItineraryItem.Kind.FLIGHT, day=target.departure_date,
        title__endswith=f"· {target.flight_number}",
    )
    days = set(cards.values_list("day", flat=True))
    cards.delete()
    _save_segments(trip, [segment_dict(row) for row in rows if row.pk != target.pk])
    clear_expected_arrival(trip, days)
    return trip
