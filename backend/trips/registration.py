"""
AI 대화로 받은 항공·숙소를 여행 등록 정보(Trip.flight_info, Hotel)로 바꾼다.

- 양식·확인 문구는 고정 문장으로 서버가 만든다(모델이 쓰지 않는다).
- 항공: 가는 편·오는 편 항목을 flight_info 형태로 옮긴다. 말하지 않은 항목은 비워 둔다.
  - update: 기존 정보에 말한 항목만 덮어쓴다 / replace: 받은 항목으로 새로 만든다.
  - 출발 시각은 대화로 받지 않는다(양식에도 없다). 날짜만 정하고 기존 출발 시각은 그대로 둔다.
- 숙소: 숙소 이름을 Google Places로 찾아 주소·좌표·전화번호를 채운다.
  - update: hotel_id로 가리킨 기존 숙소를 고친다 / add: 기존 숙소는 두고 새 숙소를 더한다.
- 같은 대화에서 아직 적용하지 않은 제안(draft)이 있으면 그 위에 이어서 고친다(앞선 변경이 사라지지 않게).
- 경로의 자동 항공·숙소 카드는 적용할 때 프론트가 만든 카드(initialCards)로 바꿔 끼운다(replace_auto_cards).
"""

import re
from datetime import date

from . import places
from .itinerary_planner import CITY_CENTERS, END_LABELS, START_LABELS
from .models import ItineraryItem

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

FLIGHT_LEG_FORM = "1. 출발: \n2. 도착: \n3. 항공사: \n4. 항공편명: \n5. 도착시간: "
FORMS = {
    "flight": (
        "양식에 맞춰 작성해 주시면 경로에 등록해 드릴게요!\n\n"
        f"- 가는 날\n{FLIGHT_LEG_FORM}\n\n- 오는 날\n{FLIGHT_LEG_FORM}"
    ),
    "hotel": (
        "양식에 맞춰 작성해 주시면 경로에 등록해 드릴게요!\n\n"
        "- 숙소\n1. 숙소명: \n2. 체크인 날짜: \n3. 체크아웃 날짜: "
    ),
}
CONFIRM_CHOICES = {
    "flight": ["기존 정보 수정", "새로 입력(덮어쓰기)"],
    "hotel": ["기본 정보 수정", "새로운 숙소 추가"],
}
CONFIRM_TEXTS = {
    "flight": "이미 등록된 공항 정보가 있습니다.\n기존 정보를 수정해 드릴까요, 아니면 새로운 정보로 변경(덮어쓰기)하시겠어요?",
    "hotel": "이미 등록된 숙소 정보가 있습니다.\n기존 숙소 정보를 수정해 드릴까요, 아니면 새로운 숙소를 추가하시겠어요?",
}


def confirm_text(target):
    return CONFIRM_TEXTS[target]


def is_registered(trip, target, draft=None):
    """등록돼 있는지 (같은 대화의 적용 전 제안도 등록된 것으로 본다)"""
    draft = draft or {}
    if target == "flight":
        return bool(draft.get("flight_info") or trip.flight_info)
    return bool(draft.get("hotels") or trip.hotels.exists())


# ------------------------------------------------------------------ #
# 항공
# ------------------------------------------------------------------ #

def _trip_date(trip, value, default):
    """여행 기간 안의 'YYYY-MM-DD'면 그 날짜, 아니면 default"""
    try:
        parsed = date.fromisoformat(value or "")
    except ValueError:
        return default
    return parsed if trip.start_date <= parsed <= trip.end_date else default


def _time(value):
    return value if value and TIME_PATTERN.match(value) else ""


def _airport(code, name):
    code = (code or "").strip().upper()[:3]
    name = (name or "").strip()[:60] or code
    return {"code": code, "name": name} if name else None


def _date_of(stamp):
    try:
        return date.fromisoformat((stamp or "")[:10])
    except ValueError:
        return None


def _apply_leg(info, leg, prefix, trip, default_day, at_keys):
    """
    한 편의 항목을 info(flight_info dict)에 옮긴다. leg에 없는(null) 항목은 그대로 둔다.
    at_keys: (출발 시각 키, 도착 시각 키). 시각은 'YYYY-MM-DDTHH:MM', 시각을 모르면 날짜만 둔다.
    """
    departure_key, arrival_key = at_keys
    if leg.departure_airport_code or leg.departure_airport_name:
        info[f"{prefix}departure_airport"] = _airport(leg.departure_airport_code, leg.departure_airport_name)
    if leg.arrival_airport_code or leg.arrival_airport_name:
        info[f"{prefix}arrival_airport"] = _airport(leg.arrival_airport_code, leg.arrival_airport_name)
    if leg.airline:
        info[f"{prefix}airline"] = leg.airline.strip()[:60]
    if leg.flight_number:
        info[f"{prefix}flight_number"] = leg.flight_number.strip().upper()[:20]

    known_day = _date_of(info.get(departure_key)) or _date_of(info.get(arrival_key))
    day = _trip_date(trip, leg.date, known_day or default_day)
    # 출발 시각은 대화로 바꾸지 않는다(기존 값 유지), 도착 시각만 받는다.
    for key, value in ((departure_key, None), (arrival_key, leg.arrival_time)):
        new_time = _time(value)
        old_time = (info.get(key) or "")[11:16]
        if new_time or old_time or leg.date:
            info[key] = f"{day.isoformat()}T{new_time or old_time}" if (new_time or old_time) else day.isoformat()


def build_flight_info(trip, change, base=None):
    """
    FlightChange -> 새 flight_info (빈 항목은 비워 둔다).
    base: 이어서 고칠 항공 정보 (같은 대화의 적용 전 제안, 없으면 등록된 정보)
    """
    current = base if base is not None else trip.flight_info
    info = dict(current or {}) if change.mode == "update" else {}
    info.setdefault("flight_number", "")
    if change.outbound:
        _apply_leg(info, change.outbound, "", trip, trip.start_date, ("departure_at", "arrival_at"))
    if change.return_leg:
        _apply_leg(info, change.return_leg, "return_", trip, trip.end_date, ("return_departure_at", "return_arrival_at"))
        # 경로의 오는 편 카드는 귀국 도착 일시로 날짜를 정하므로, 시각을 모르면 날짜만이라도 둔다.
        if not info.get("return_arrival_at"):
            day = _date_of(info.get("return_departure_at")) or trip.end_date
            info["return_arrival_at"] = day.isoformat()
    # 경로의 가는 편 카드 날짜 (시각을 모르면 날짜만)
    if not info.get("departure_at"):
        info["departure_at"] = (_date_of(info.get("arrival_at")) or trip.start_date).isoformat()
    return info


# ------------------------------------------------------------------ #
# 숙소
# ------------------------------------------------------------------ #

def _hotel_dict(hotel):
    return {
        "id": hotel.id, "name": hotel.name, "address": hotel.address, "place_id": hotel.place_id,
        "latitude": hotel.latitude, "longitude": hotel.longitude, "phone": hotel.phone,
        "city_code": hotel.city_code, "check_in": hotel.check_in, "check_out": hotel.check_out,
    }


def _trip_center(trip):
    for dest in trip.destinations or []:
        center = CITY_CENTERS.get((dest.get("city_code") or "").upper())
        if center:
            return center
    return (None, None)


def _find_hotel(trip, query):
    try:
        return places.search_place(query, *_trip_center(trip))
    except places.PlacesError:
        return None


def _draft_hotel(hotel):
    """적용 전 제안의 숙소 (날짜 문자열 -> date)"""
    data = dict(hotel)
    data["check_in"] = date.fromisoformat(str(data["check_in"]))
    data["check_out"] = date.fromisoformat(str(data["check_out"])) if data.get("check_out") else None
    return data


def build_hotels(trip, change, base=None):
    """
    HotelChange -> (최종 숙소 목록, 찾지 못한 숙소 이름).
    목록 항목: _hotel_dict 형태 + status(new|updated|same). 새 숙소는 id가 None.
    base: 이어서 고칠 숙소 목록 (같은 대화의 적용 전 제안, 없으면 등록된 숙소). 기존 숙소는 항상 남긴다.
    update는 hotel_id(새 숙소면 목록 순서 key)로 가리킨 숙소만 고치고, add는 새 숙소를 더한다.
    """
    if base is not None:
        final = [_draft_hotel(hotel) for hotel in base]
    else:
        final = [dict(_hotel_dict(hotel), status="same") for hotel in trip.hotels.all()]
    by_id = {hotel["id"]: hotel for hotel in final if hotel.get("id")}
    unresolved = []

    for entry in change.hotels:
        target = by_id.get(entry.hotel_id) if entry.hotel_id else None
        if change.mode == "update" and target is None:
            # 수정할 숙소를 못 찾으면(아직 저장 전인 새 숙소 등) 이름이 같은 숙소를 고친다.
            target = next((hotel for hotel in final if entry.name and hotel["name"] == entry.name), None)
            if target is None:
                continue
        if target is None and not (entry.name or entry.search_query):
            continue
        hotel = target if target is not None else {
            "id": None, "name": "", "address": "", "place_id": "", "latitude": None, "longitude": None,
            "phone": "", "city_code": "", "check_in": trip.start_date, "check_out": trip.end_date, "status": "new",
        }
        if entry.name or entry.search_query:
            detail = _find_hotel(trip, entry.search_query or entry.name)
            if not detail or detail.get("latitude") is None:
                unresolved.append(entry.name or entry.search_query)
                continue
            hotel.update(
                name=(detail.get("name") or entry.name or "")[:150], address=(detail.get("address") or "")[:255],
                place_id=detail.get("place_id", ""), latitude=detail.get("latitude"),
                longitude=detail.get("longitude"), phone=(detail.get("phone") or "")[:40],
            )
        hotel["check_in"] = _trip_date(trip, entry.check_in, hotel["check_in"])
        hotel["check_out"] = _trip_date(trip, entry.check_out, hotel["check_out"])
        if hotel["check_out"] and hotel["check_out"] < hotel["check_in"]:
            hotel["check_out"] = hotel["check_in"]
        if target is not None:
            # 아직 저장 전인 새 숙소를 고친 경우는 '추가'로 둔다.
            target["status"] = "new" if target.get("id") is None else "updated"
        else:
            final.append(hotel)

    for hotel in final:
        hotel["nights"] = (hotel["check_out"] - hotel["check_in"]).days if hotel["check_out"] else None
    final.sort(key=lambda hotel: hotel["check_in"])
    return final, unresolved


def removed_hotels(trip, final):
    kept = {hotel["id"] for hotel in final if hotel["id"]}
    return [{"id": hotel.id, "title": hotel.name} for hotel in trip.hotels.all() if hotel.id not in kept]


def save_hotels(trip, hotels):
    """최종 숙소 목록대로 저장한다(목록에 없는 기존 숙소는 지운다)."""
    fields = ("name", "address", "place_id", "latitude", "longitude", "phone", "city_code", "check_in", "check_out")
    owned = {hotel.id: hotel for hotel in trip.hotels.all()}
    keep = {hotel["id"] for hotel in hotels if hotel.get("id") in owned}
    trip.hotels.exclude(id__in=keep).delete()
    for data in hotels:
        values = {field: data.get(field) for field in fields}
        values["address"] = values["address"] or ""
        values["phone"] = values["phone"] or ""
        values["place_id"] = values["place_id"] or ""
        values["city_code"] = values["city_code"] or ""
        if data.get("id") in keep:
            hotel = owned[data["id"]]
            for field, value in values.items():
                setattr(hotel, field, value)
            hotel.save()
        else:
            trip.hotels.create(**values)


# ------------------------------------------------------------------ #
# 경로의 자동 항공·숙소 카드
# ------------------------------------------------------------------ #

AUTO_KINDS = (ItineraryItem.Kind.FLIGHT, ItineraryItem.Kind.HOTEL)


def replace_auto_cards(trip, days, cards):
    """
    days({date: [cards]})에서 자동 항공·숙소 카드를 빼고, 새 카드(cards: day 포함)를 넣는다.
    그날의 시작 카드(체크아웃·출국·숙박)는 맨 앞에, 끝 카드(체크인·귀국)는 맨 뒤에 받은 순서대로 둔다.
    지울 자동 카드 id 목록을 돌려준다.
    """
    auto_ids = set(
        trip.itinerary_items.filter(source=ItineraryItem.Source.AUTO, kind__in=AUTO_KINDS).values_list("id", flat=True)
    )
    for day in days:
        days[day] = [card for card in days[day] if card.get("id") not in auto_ids]
    for day in days:
        new = [dict(card, source=ItineraryItem.Source.AUTO) for card in cards if card.get("day") == day]
        start = [card for card in new if card.get("time_label") in START_LABELS]
        end = [card for card in new if card.get("time_label") in END_LABELS]
        middle = [card for card in new if card not in start and card not in end]
        days[day] = start + days[day] + middle + end
    return auto_ids


# ------------------------------------------------------------------ #
# 경로에서 자동 항공·숙소 카드를 지웠을 때 등록 정보 맞추기
# ------------------------------------------------------------------ #

OUTBOUND_KEYS = ("airline", "flight_number", "departure_at", "arrival_at", "departure_airport", "arrival_airport")
RETURN_KEYS = tuple(f"return_{key}" for key in OUTBOUND_KEYS)


def _registered_hotel(trip, item):
    """자동 숙소 카드에 해당하는 등록 숙소 (이름이 같고 그날이 숙박 기간 안인 숙소)"""
    for hotel in trip.hotels.filter(name=item.title):
        if hotel.check_in <= item.day and (hotel.check_out is None or item.day <= hotel.check_out):
            return hotel
    return None


HOTEL_ENDS = ("체크인", "체크아웃")


def sync_after_card_delete(trip, item):
    """
    경로에서 자동 생성된 항공·숙소 카드(item)를 지우기 전에 등록 정보를 맞춘다.
    (바뀌었는지, 함께 지울 다른 카드 id 목록)을 돌려준다.
    - 가는 편(출국)·오는 편(귀국) 카드: 그 편의 항목만 지운다. 두 편 모두 없으면 항공 미등록.
    - 숙소 체크인·체크아웃 카드: 그 숙소를 지우고, 그 숙소의 체크인·숙박·체크아웃 카드도 함께 지운다
      (화면에서 사용자에게 먼저 확인한다). 숙박 카드만 지울 때는 숙소 정보를 그대로 둔다.
    """
    if item.source != ItineraryItem.Source.AUTO:
        return False, []
    if item.kind == ItineraryItem.Kind.FLIGHT:
        keys = {"출국": OUTBOUND_KEYS, "귀국": RETURN_KEYS}.get(item.time_label)
        if not keys or not trip.flight_info:
            return False, []
        info = {key: value for key, value in trip.flight_info.items() if key not in keys}
        # 여행 응답 형식상 편명·출국 일시 키는 있어야 하므로 비워서 둔다(화면은 빈 값을 '없음'으로 본다).
        info.setdefault("flight_number", "")
        info.setdefault("departure_at", "")
        trip.flight_info = info if any(info.get(key) for key in OUTBOUND_KEYS + RETURN_KEYS) else None
        trip.save(update_fields=["flight_info", "updated_at"])
        return True, []
    if item.kind == ItineraryItem.Kind.HOTEL and item.time_label in HOTEL_ENDS:
        hotel = _registered_hotel(trip, item)
        if hotel is None:
            return False, []
        others = list(
            trip.itinerary_items.filter(source=ItineraryItem.Source.AUTO, kind=ItineraryItem.Kind.HOTEL, title=item.title,
                                        day__gte=hotel.check_in, day__lte=hotel.check_out or trip.end_date)
            .exclude(pk=item.pk)
            .values_list("id", flat=True)
        )
        hotel.delete()
        return True, others
    return False, []


# ------------------------------------------------------------------ #
# 장소 직접 추가로 숙소 등록 (체크인~체크아웃)
# ------------------------------------------------------------------ #

def hotel_cards(trip, hotel):
    """
    등록 숙소 -> 경로의 숙소 카드 (프론트 initialCards의 숙소 카드와 같은 모양).
    체크인 날(체크인, 'N박'), 사이 날(숙박), 체크아웃 날(체크아웃). 여행 기간 밖의 날은 만들지 않는다.
    """
    cards = []
    total = (hotel.check_out - hotel.check_in).days if hotel.check_out else 0
    for offset in range(total + 1):
        day = date.fromordinal(hotel.check_in.toordinal() + offset)
        if not trip.start_date <= day <= trip.end_date:
            continue
        label = "체크인" if offset == 0 else ("체크아웃" if offset == total else "숙박")
        cards.append({
            "day": day,
            "kind": ItineraryItem.Kind.HOTEL,
            "source": ItineraryItem.Source.AUTO,
            "title": hotel.name,
            "time": "",
            "time_label": label,
            "subtitle": f"{total}박" if label == "체크인" and total else "",
            "stops": [{"kind": "hotel", "caption": label, "label": hotel.address or hotel.name,
                       "lat": hotel.latitude, "lng": hotel.longitude}],
            "phone": hotel.phone,
        })
    return cards


def insert_auto_cards(days, cards):
    """
    자동 숙소 카드를 그날 일정에 끼운다(다른 카드는 그대로).
    체크아웃은 맨 앞, 숙박은 그날 시작 카드들(체크아웃·출국·숙박) 뒤, 체크인은 귀국편 앞(없으면 맨 뒤).
    """
    for card in cards:
        cards_of_day = days.setdefault(card["day"], [])
        label = card["time_label"]
        if label == "체크아웃":
            index = 0
        elif label in START_LABELS:
            index = next((i for i, c in enumerate(cards_of_day) if c.get("time_label") not in START_LABELS),
                         len(cards_of_day))
        else:
            index = next((i for i, c in enumerate(cards_of_day) if c.get("time_label") == "귀국"), len(cards_of_day))
        cards_of_day.insert(index, card)
