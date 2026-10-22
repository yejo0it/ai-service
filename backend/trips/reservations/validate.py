"""
예약 정보 정규화·검증. AI가 추출한 값과 사용자가 고친 값이 같은 경로를 지난다(둘 다 신뢰하지 않는다).

- normalize: 모르는 키·과한 길이·제어 문자를 정리하고 날짜·시각·공항 코드·편명을 표준 형식으로 맞춘다.
  형식이 틀린 값은 지우지 않고(최대 20자) 그대로 두어 화면에서 고치게 한다.
- check: 필수값·형식·순서를 확인해 막는 오류(errors)와 알려 주기만 하는 경고(warnings)로 나눈다.
  경로(path)는 `itineraries.0.segments.1.departure_date`처럼 화면의 입력 칸과 맞춘다.
- 출발·도착 시각은 각 공항의 현지 시각이라 시차 때문에 도착이 더 빠르게 보일 수 있다. 그래서 순서 이상은 경고만 한다.
"""

import re
from datetime import date

from .schemas import FLIGHT, KINDS

MAX_ITINERARIES = 6
MAX_SEGMENTS = 12
MAX_STAYS = 10
MAX_NOTES = 3

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_CODE = re.compile(r"^[A-Z]{3}$")
_FLIGHT_NUMBER = re.compile(r"^[A-Z0-9]{2}\d{1,4}[A-Z]?$")


class ReservationDataError(Exception):
    """분석 결과·수정값의 전체 구조가 잘못된 경우(필드 단위 오류가 아님)."""


def clean_text(value, limit):
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", _CONTROL.sub(" ", value)).strip()
    return text[:limit] or None


def is_valid_date(value):
    if not (isinstance(value, str) and _DATE.match(value)):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_valid_time(value):
    return isinstance(value, str) and bool(re.match(r"^([01]\d|2[0-3]):[0-5]\d$", value))


def normalize_date(value):
    text = clean_text(value, 20)
    return text  # 형식이 틀리면 그대로 두고 check가 알린다.


def normalize_time(value):
    text = clean_text(value, 20)
    if text:
        match = _TIME.match(text)
        if match:
            return f"{int(match.group(1)):02d}:{match.group(2)}"
    return text


def normalize_code(value):
    text = clean_text(value, 10)
    return text.upper() if text else None


def normalize_flight_number(value):
    text = clean_text(value, 12)
    if not text:
        return None
    compact = re.sub(r"[\s-]", "", text).upper()
    return compact if _FLIGHT_NUMBER.match(compact) else text.upper()


def _notes(value):
    if not isinstance(value, list):
        return []
    return [note for note in (clean_text(item, 120) for item in value[:MAX_NOTES]) if note]


def _list(value, limit):
    return [item for item in value[:limit] if isinstance(item, dict)] if isinstance(value, list) else []


def normalize_segment(raw):
    return {
        "airline_name": clean_text(raw.get("airline_name"), 60),
        "flight_number": normalize_flight_number(raw.get("flight_number")),
        "departure_airport_code": normalize_code(raw.get("departure_airport_code")),
        "departure_airport_name": clean_text(raw.get("departure_airport_name"), 80),
        "arrival_airport_code": normalize_code(raw.get("arrival_airport_code")),
        "arrival_airport_name": clean_text(raw.get("arrival_airport_name"), 80),
        "departure_date": normalize_date(raw.get("departure_date")),
        "departure_time": normalize_time(raw.get("departure_time")),
        "arrival_date": normalize_date(raw.get("arrival_date")),
        "arrival_time": normalize_time(raw.get("arrival_time")),
        "direction": raw.get("direction") if raw.get("direction") in ("outbound", "return") else None,
        "notes": _notes(raw.get("notes")),
    }


def normalize_stay(raw):
    return {
        "name": clean_text(raw.get("name"), 150),
        "address": clean_text(raw.get("address"), 255),
        "check_in_date": normalize_date(raw.get("check_in_date")),
        "check_out_date": normalize_date(raw.get("check_out_date")),
        "check_in_time": normalize_time(raw.get("check_in_time")),
        "check_out_time": normalize_time(raw.get("check_out_time")),
        "status": clean_text(raw.get("status"), 40),
        "notes": _notes(raw.get("notes")),
    }


def normalize(kind, raw):
    """원본(딕셔너리) -> 표준 형식의 예약 정보 객체. 구조가 아예 틀리면 ReservationDataError."""
    if kind not in KINDS or not isinstance(raw, dict):
        raise ReservationDataError("예약 정보 형식이 올바르지 않아요.")
    if kind == FLIGHT:
        itineraries = [
            {
                "status": clean_text(item.get("status"), 40),
                "segments": [normalize_segment(seg) for seg in _list(item.get("segments"), MAX_SEGMENTS)],
            }
            for item in _list(raw.get("itineraries"), MAX_ITINERARIES)
        ]
        return {"itineraries": itineraries}
    return {"stays": [normalize_stay(stay) for stay in _list(raw.get("stays"), MAX_STAYS)]}


# ---------------------------------------------------------------- 검증

def _issue(path, message):
    return {"path": path, "message": message}


def _check_format(errors, path, value, valid, example):
    if value and not valid(value):
        errors.append(_issue(path, f"형식이 올바르지 않아요. (예: {example})"))


def _check_segment(index, number, segment, errors, warnings):
    base = f"itineraries.{index}.segments.{number}"
    required = (
        ("flight_number", "항공편명을 입력해 주세요."),
        ("departure_airport_code", "출발 공항 코드를 입력해 주세요."),
        ("arrival_airport_code", "도착 공항 코드를 입력해 주세요."),
        ("departure_date", "출발 날짜를 입력해 주세요."),
        ("departure_time", "출발 시각을 입력해 주세요."),
    )
    for field, message in required:
        if not segment[field]:
            errors.append(_issue(f"{base}.{field}", message))

    _check_format(errors, f"{base}.flight_number", segment["flight_number"], lambda v: bool(_FLIGHT_NUMBER.match(v)), "KE703")
    for field in ("departure_airport_code", "arrival_airport_code"):
        _check_format(errors, f"{base}.{field}", segment[field], lambda v: bool(_CODE.match(v)), "ICN")
    for field in ("departure_date", "arrival_date"):
        _check_format(errors, f"{base}.{field}", segment[field], is_valid_date, "2026-11-10")
    for field in ("departure_time", "arrival_time"):
        _check_format(errors, f"{base}.{field}", segment[field], is_valid_time, "09:30")

    if (
        segment["departure_airport_code"]
        and segment["departure_airport_code"] == segment["arrival_airport_code"]
        and _CODE.match(segment["departure_airport_code"])
    ):
        errors.append(_issue(f"{base}.arrival_airport_code", "출발 공항과 도착 공항이 같아요."))

    if not segment["airline_name"]:
        warnings.append(_issue(f"{base}.airline_name", "항공사가 비어 있어요."))
    if not segment["arrival_date"] or not segment["arrival_time"]:
        warnings.append(_issue(f"{base}.arrival_date", "도착 날짜·시각이 비어 있어요."))

    # 도착이 출발보다 빠르게 보이는 경우(시차·날짜 변경선 때문일 수 있어 경고만 한다)
    if all(is_valid_date(segment[f]) for f in ("departure_date", "arrival_date")):
        departure = (segment["departure_date"], segment["departure_time"] if is_valid_time(segment["departure_time"]) else "00:00")
        arrival = (segment["arrival_date"], segment["arrival_time"] if is_valid_time(segment["arrival_time"]) else "00:00")
        if arrival < departure:
            warnings.append(
                _issue(f"{base}.arrival_date", "도착이 출발보다 빨라요. 시차 때문이 아니라면 날짜와 시각을 확인해 주세요.")
            )


def _check_flight(document, errors, warnings):
    if not document["itineraries"]:
        errors.append(_issue("itineraries", "항공편 구간을 한 개 이상 입력해 주세요."))
    for index, itinerary in enumerate(document["itineraries"]):
        if not itinerary["segments"]:
            errors.append(_issue(f"itineraries.{index}.segments", "항공편 구간을 한 개 이상 입력해 주세요."))
        for number, segment in enumerate(itinerary["segments"]):
            _check_segment(index, number, segment, errors, warnings)
        # 한 예약 안에서 앞 구간의 도착 공항과 다음 구간의 출발 공항이 이어지는지
        for number in range(1, len(itinerary["segments"])):
            previous, current = itinerary["segments"][number - 1], itinerary["segments"][number]
            if (
                previous["arrival_airport_code"]
                and current["departure_airport_code"]
                and previous["arrival_airport_code"] != current["departure_airport_code"]
            ):
                warnings.append(
                    _issue(
                        f"itineraries.{index}.segments.{number}.departure_airport_code",
                        "앞 구간의 도착 공항과 이어지지 않아요. (왕복이면 정상일 수 있어요)",
                    )
                )


def _check_hotel(document, errors, warnings):
    if not document["stays"]:
        errors.append(_issue("stays", "숙소를 한 개 이상 입력해 주세요."))
    for index, stay in enumerate(document["stays"]):
        base = f"stays.{index}"
        for field, message in (
            ("name", "숙소 이름을 입력해 주세요."),
            ("check_in_date", "체크인 날짜를 입력해 주세요."),
            ("check_out_date", "체크아웃 날짜를 입력해 주세요."),
        ):
            if not stay[field]:
                errors.append(_issue(f"{base}.{field}", message))
        for field in ("check_in_date", "check_out_date"):
            _check_format(errors, f"{base}.{field}", stay[field], is_valid_date, "2026-11-10")
        for field in ("check_in_time", "check_out_time"):
            _check_format(errors, f"{base}.{field}", stay[field], is_valid_time, "15:00")
        if is_valid_date(stay["check_in_date"]) and is_valid_date(stay["check_out_date"]):
            if stay["check_out_date"] < stay["check_in_date"]:
                errors.append(_issue(f"{base}.check_out_date", "체크아웃이 체크인보다 빨라요."))
            elif stay["check_out_date"] == stay["check_in_date"]:
                warnings.append(_issue(f"{base}.check_out_date", "체크인과 체크아웃이 같은 날이에요."))
        if not stay["address"]:
            warnings.append(_issue(f"{base}.address", "주소가 비어 있어요."))


def check(kind, document):
    """정규화된 객체 -> (errors, warnings). errors가 비어 있어야 '검증된 예약 정보'다."""
    errors, warnings = [], []
    (_check_flight if kind == FLIGHT else _check_hotel)(document, errors, warnings)
    return errors, warnings


def build_result(kind, raw):
    """정규화 + 검증을 한 번에. analyze와 validate API가 같은 모양으로 돌려준다."""
    document = normalize(kind, raw)
    errors, warnings = check(kind, document)
    return {"kind": kind, "document": document, "valid": not errors, "errors": errors, "warnings": warnings}
