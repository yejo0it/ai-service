"""
일정 카드 사이 이동 구간 상세(여행 상세의 '이동 경로' 표시). 방문 순서는 정하지 않고, 저장된 순서의 이어지는 카드 사이를 계산한다.

구간마다 한 가지 수단만 고른다:
1. 도보 20분 이하(Google Routes 도보) → 도보
2. 일본 → NAVITIME 대중교통(노선·승하차역·시각·요금). 그 밖의 지원 지역 → Google Routes 대중교통(노선·승하차 정류장·정류장 수)
3. 대중교통 정보가 없으면 자동차(택시) 이동 시간, 그것도 없으면 도보, 모두 없으면 '경로 없음'
이동 시간·노선은 Google·NAVITIME이 돌려준 값만 쓰고, 정보가 없으면 만들어 채우지 않는다.

비용·약관: 구간 결과는 DB에 저장하지 않고 서버 메모리에 짧게(ROUTES_CACHE_TTL_SECONDS) 캐시한다. 호출 수는 기존 한도
(Google 요소 수·NAVITIME 호출 수)를 함께 쓰며, 한도에 닿으면 남은 구간은 도보/자동차 또는 '경로 없음'으로 보인다.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from django.conf import settings
from django.core.cache import cache

from . import routes
from . import transit as navitime
from .itinerary_planner import entry_point, exit_point, stay_minutes
from . import untranslated
from .line_names import korean_line_and_type
from .station_names import (
    display_station,
    korean_company,
    korean_gateway,
    korean_station,
    normalize,
    station_labels,
)

WALK_ONLY_MAX_MIN = 20  # 이 시간 이하면 도보만 보여준다
DEFAULT_LINE_COLOR = "#64748b"
NOT_FOUND = "not_found"
DEFAULT_DEPART_MIN = 11 * 60  # 출발 시각을 모르면 시간표 조회에 쓰는 대표 시각(표시하지 않음)


def format_distance(meters):
    return f"{round(meters / 10) * 10}m" if meters < 1000 else f"{meters / 1000:.1f}km"


def _hhmm(value):
    """'2026-10-22T10:04:00+09:00' -> '10:04' (현지 시각 그대로)."""
    return value[11:16] if isinstance(value, str) and len(value) >= 16 else ""


def _clock(minutes):
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def _walk_step(minutes, meters, start="", target=""):
    text = f"도보 {minutes}분" + (f" · {format_distance(meters)}" if meters else "")
    if target:
        text += f" · {target}까지"
    return {"type": "walk", "minutes": minutes, "meters": meters, "start_time": start, "description": text}


# --------------------------------------------------------------------------- #
# 응답 해석 (순수 함수)
# --------------------------------------------------------------------------- #


_HANGUL = re.compile(r"[가-힣]")


def _coord(point):
    coord = point.get("coord") or {}
    return coord.get("lat"), coord.get("lon")


def _is_station(point):
    return "station" in (point.get("node_types") or [])


def _point_text(point):
    """문장용 지점 표기: 역은 '시부야역(渋谷駅) 동쪽 출구', 그 밖의 지점은 이름 그대로(정류장 등)."""
    name = point.get("name", "")
    if not _is_station(point):
        return name
    lat, lng = _coord(point)
    text = display_station(name, lat, lng, point.get("node_id"))
    gateway = korean_gateway(point.get("gateway", ""))
    return f"{text} {gateway}" if gateway else text


def _numbers(point, key):
    """역 번호(JY20). 번호가 여럿이면 '·'로 잇는다."""
    items = (point.get("numbering") or {}).get(key) or []
    return "·".join(f"{item.get('symbol', '')}{item.get('number', '')}" for item in items if item.get("number"))


def _navitime_walk(index, sections, minutes, meters, start):
    """도보 안내 문장: [역에서] 도보 N분 · 거리 · [역까지] (한국어 템플릿)."""
    previous = sections[index - 1] if index > 0 else {}
    following = next((s for s in sections[index + 1:] if s.get("type") == "point"), {})
    origin = f"{_point_text(previous)}에서 " if previous.get("type") == "point" and _is_station(previous) else ""
    target = ""
    if following.get("name") and following.get("name") != "goal" and _is_station(following):
        target = f" · {_point_text(following)}까지"
    text = f"{origin}도보 {minutes}분" + (f" · {format_distance(meters)}" if meters else "") + target
    return {"type": "walk", "minutes": minutes, "meters": meters, "start_time": start, "description": text}


def _navitime_transit(section, board, alight, minutes, start):
    """탑승 구간: 노선·운영사·행선지·역(한국어 + 원어)·역 번호·환승 시간."""
    transport = section.get("transport") or {}
    links = transport.get("links") or [{}]
    first, last = links[0], links[-1]
    from_name = first.get("from", {}).get("name") or board.get("name", "")
    to_name = last.get("to", {}).get("name") or alight.get("name", "")
    from_lat, from_lng = _coord(board)
    to_lat, to_lng = _coord(alight)
    from_ko, from_ja = station_labels(from_name, from_lat, from_lng, board.get("node_id") or first.get("from", {}).get("id"))
    to_ko, to_ja = station_labels(to_name, to_lat, to_lng, alight.get("node_id") or last.get("to", {}).get("id"))
    line = korean_line_and_type(transport.get("name") or section.get("line_name", ""), transport.get("type", ""))
    company = transport.get("company", {}).get("name", "")
    destination = (first.get("destination") or {}).get("name", "")
    dest_ko = korean_station(destination) if destination else None
    if destination and not dest_ko:
        untranslated.record_station(destination)  # 행선지는 이름만 있다
    raw_line = transport.get("name") or section.get("line_name", "")
    if raw_line and not _HANGUL.search(line["line_name"]):
        untranslated.record_line(raw_line, company)
    transfer_seconds = int(section.get("transfer_seconds") or 0)
    return {
        "type": "transit",
        "minutes": minutes,
        "start_time": start,
        # 노선명·운영사·역 이름은 한국어(사전·데이터에 있을 때)와 원어를 함께 준다. 확보하지 못하면 원어 그대로다.
        "line_name": line["line_name"],
        "line_name_ja": line["line_name_ja"],
        # 열차 종별(쾌속·신쾌속·특급 …)은 노선명과 따로 준다. 보통(각역 정차)은 비워 둔다.
        "train_type": line["train_type"],
        "train_type_ja": line["train_type_ja"],
        "line_color": transport.get("color") or DEFAULT_LINE_COLOR,
        "operator": korean_company(company),
        "operator_ja": normalize(company),
        "from_stop": from_ko,
        "from_stop_ja": from_ja,
        "to_stop": to_ko,
        "to_stop_ja": to_ja,
        "from_number": _numbers(board, "departure"),
        "to_number": _numbers(alight, "arrival"),
        "direction": (f"{dest_ko[:-1] if dest_ko.endswith('역') else dest_ko}행" if dest_ko else f"{normalize(destination)}行") if destination else "",
        "direction_ja": f"{normalize(destination)}行" if destination else "",
        "transfer_minutes": round(transfer_seconds / 60) if transfer_seconds >= 30 else None,
        "stop_count": 0,  # NAVITIME 응답에는 통과 역 수가 없다
    }


def parse_navitime(payload, with_times):
    """NAVITIME route_transit 응답의 첫 경로 -> {"total_minutes", "meters", "fare_label", "steps"}. 해석할 수 없으면 None."""
    try:
        item = payload["items"][0]
        move = item["summary"]["move"]
        sections = item["sections"]
        total = int(move["time"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None

    def point_after(index):
        for section in sections[index + 1:]:
            if section.get("type") == "point":
                return section
        return {}

    def point_before(index):
        for section in reversed(sections[:index]):
            if section.get("type") == "point":
                return section
        return {}

    steps = []
    for index, section in enumerate(sections):
        if section.get("type") != "move":
            continue
        minutes = int(section.get("time", 0))
        meters = int(section.get("distance", 0))
        start = _hhmm(section.get("from_time")) if with_times else ""
        if section.get("move") == "walk":
            if minutes == 0 and meters == 0:
                continue
            steps.append(_navitime_walk(index, sections, minutes, meters, start))
            continue
        steps.append(_navitime_transit(section, point_before(index), point_after(index), minutes, start))
    if not steps:
        return None
    fare = (move.get("reference_fare") or {})
    amount = fare.get("lowest_total_ic") or fare.get("lowest_total_ticket")
    return {
        "total_minutes": total,
        "meters": int(move.get("distance", 0)),
        "fare_label": f"¥{int(amount):,}" if amount else None,
        "steps": steps,
    }


def _seconds(value):
    try:
        return int(float(str(value).rstrip("s")))
    except (TypeError, ValueError):
        return 0


def _local_minutes(iso_utc, tz):
    try:
        moment = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(tz)
    except (AttributeError, ValueError):
        return None
    return moment.hour * 60 + moment.minute


def parse_google_transit(payload, tz, depart_minute, with_times):
    """Google computeRoutes(TRANSIT) 응답의 첫 경로 -> NAVITIME과 같은 모양. 해석할 수 없으면 None."""
    try:
        route = payload["routes"][0]
        raw_steps = route["legs"][0]["steps"]
        total = max(1, round(_seconds(route["duration"]) / 60))
    except (KeyError, IndexError, TypeError):
        return None

    # 연속된 도보 구간은 하나로 합치고, 0분·0m인 짧은 구간은 버린다.
    merged = []
    for step in raw_steps:
        if step.get("travelMode") == "TRANSIT" and step.get("transitDetails"):
            merged.append(step)
        elif step.get("travelMode") == "WALK":
            seconds, meters = _seconds(step.get("staticDuration")), int(step.get("distanceMeters", 0))
            if merged and merged[-1].get("travelMode") == "WALK":
                merged[-1]["_seconds"] += seconds
                merged[-1]["_meters"] += meters
            else:
                merged.append({"travelMode": "WALK", "_seconds": seconds, "_meters": meters})

    steps, clock = [], depart_minute
    for index, step in enumerate(merged):
        if step["travelMode"] == "WALK":
            minutes = round(step["_seconds"] / 60)
            if minutes == 0 and step["_meters"] == 0:
                continue
            following = next((s for s in merged[index + 1:] if s["travelMode"] == "TRANSIT"), None)
            target = following["transitDetails"]["stopDetails"]["departureStop"].get("name", "") if following else ""
            steps.append(_walk_step(minutes, step["_meters"], _clock(clock) if with_times and clock is not None else "", target))
            if clock is not None:
                clock += minutes
            continue
        details = step["transitDetails"]
        stops = details.get("stopDetails", {})
        line = details.get("transitLine", {})
        departed = _local_minutes(stops.get("departureTime"), tz)
        arrived = _local_minutes(stops.get("arrivalTime"), tz)
        minutes = round(_seconds(step.get("staticDuration")) / 60)
        if departed is not None and arrived is not None:
            minutes = (arrived - departed) % (24 * 60) or minutes
        steps.append(
            {
                "type": "transit",
                "minutes": max(1, minutes),
                "start_time": _clock(departed) if with_times and departed is not None else "",
                "line_name": line.get("nameShort") or line.get("name", ""),
                "line_color": line.get("color") or DEFAULT_LINE_COLOR,
                "from_stop": stops.get("departureStop", {}).get("name", ""),
                "to_stop": stops.get("arrivalStop", {}).get("name", ""),
                "stop_count": int(details.get("stopCount", 0)),
            }
        )
        if arrived is not None:
            clock = arrived
    if not steps:
        return None
    return {"total_minutes": total, "meters": int(route.get("distanceMeters", 0)), "fare_label": None, "steps": steps}


# --------------------------------------------------------------------------- #
# 구간 하나
# --------------------------------------------------------------------------- #


def _cache_key(origin, destination, minute, with_times):
    bucket = "x" if minute is None else str(minute // 30 * 30)
    return f"leg:{origin[0]:.5f},{origin[1]:.5f}:{destination[0]:.5f},{destination[1]:.5f}:{bucket}:{int(with_times)}"


def build_leg(origin, destination, day, minute, budget, transit_budget):
    """
    origin→destination 구간의 이동 정보(수단·소요·단계). 계산할 수 없으면 None(지원 지역 밖·같은 지점).
    경로를 찾지 못하면 {"status": "not_found"}.
    minute: 출발 시각(분). 모르면 None이며, 단계별 시각은 비운다.
    """
    country = routes.service_area(origin)
    if country is None or routes.service_area(destination) is None or origin == destination:
        return None
    with_times = minute is not None
    key = _cache_key(origin, destination, minute, with_times)
    hit = cache.get(key)
    if hit is not None:
        return hit
    depart = minute if minute is not None else DEFAULT_DEPART_MIN
    leg = _compute(origin, destination, day, depart, with_times, country, budget, transit_budget)
    cache.set(key, leg, settings.ROUTES_CACHE_TTL_SECONDS)
    return leg


def _matrix_leg(origin, destination, mode, budget):
    try:
        result = routes.travel_matrix([origin, destination], mode, budget=budget)
    except routes.RoutesError:
        return None
    return result.get((0, 1))


def _compute(origin, destination, day, depart, with_times, country, budget, transit_budget):
    walk = _matrix_leg(origin, destination, "WALK", budget)
    if walk and walk.seconds <= WALK_ONLY_MAX_MIN * 60:
        minutes = max(1, round(walk.seconds / 60))
        return {"status": "ok", "mode": "walk", "total_minutes": minutes, "fare_label": None,
                "steps": [_walk_step(minutes, walk.meters)]}

    route = None
    if country == "JP":
        route = _navitime_route(origin, destination, day, depart, with_times, transit_budget)
    else:
        route = _google_transit(origin, destination, day, depart, with_times, country, budget)
    if route:
        return {"status": "ok", "mode": "transit", "total_minutes": route["total_minutes"],
                "fare_label": route["fare_label"], "steps": route["steps"]}

    drive = _matrix_leg(origin, destination, "DRIVE", budget)
    if drive:
        minutes = max(1, round(drive.seconds / 60))
        return {"status": "ok", "mode": "drive", "total_minutes": minutes, "fare_label": None,
                "steps": [{"type": "drive", "minutes": minutes, "meters": drive.meters, "start_time": "",
                           "description": f"택시·차량 {minutes}분 · {format_distance(drive.meters)}"}]}
    if walk:
        minutes = max(1, round(walk.seconds / 60))
        return {"status": "ok", "mode": "walk", "total_minutes": minutes, "fare_label": None,
                "steps": [_walk_step(minutes, walk.meters)]}
    return {"status": NOT_FOUND, "mode": "transit", "total_minutes": 0, "fare_label": None, "steps": []}


def _navitime_route(origin, destination, day, depart, with_times, transit_budget):
    """NAVITIME 대중교통 경로 한 건(월 호출 한도·응답 헤더의 남은 횟수를 지킨다). 정보가 없으면 None."""
    if not navitime.enabled():
        return None
    try:
        transit_budget.take()
    except navitime.TransitBudgetExceeded:
        return None
    payload, remaining = navitime._request(origin, destination, navitime.start_time_for(day, depart))
    if remaining is not None:
        cache.set("navitime:remaining", remaining, 60 * 60 * 24)
    return parse_navitime(payload, with_times) if payload else None


def _google_transit(origin, destination, day, depart, with_times, country, budget):
    try:
        payload = routes.compute_transit_route(origin, destination, day, depart, country, budget)
    except routes.RoutesError:
        return None
    return parse_google_transit(payload, routes._zone(country), depart, with_times) if payload else None


# --------------------------------------------------------------------------- #
# 하루 전체
# --------------------------------------------------------------------------- #


def _departure_minute(item):
    """이 일정에서 떠나는 시각(분). 정한 시간 → 예상 도착 + 체류. 모르면 None."""
    if item.time:
        return item.time.hour * 60 + item.time.minute + stay_minutes({"kind": item.kind, "stay_minutes": item.stay_minutes})
    if item.expected_arrival:
        return (item.expected_arrival.hour * 60 + item.expected_arrival.minute
                + stay_minutes({"kind": item.kind, "stay_minutes": item.stay_minutes}))
    return None


def day_legs(items, day, user_id=None):
    """
    items: 그날 일정(순서대로). 두 번째 카드부터 '직전 카드 → 이 카드' 구간을 계산한다.
    항공편 카드 앞에는 구간이 없고, 항공편 다음 카드는 도착 공항에서 출발한다.
    돌려주는 값: [{"from_item_id", "to_item_id", "status", "mode", "total_minutes", "fare_label", "steps"}]
    (지원 지역 밖·계산할 수 없는 구간은 빠진다)
    """
    if not routes.enabled():
        return []
    budget, transit_budget = routes.Budget(user_id), navitime.TransitBudget()
    jobs = []
    for previous, current in zip(items, items[1:]):
        if current.kind == "flight":
            continue
        origin = exit_point({"stops": previous.stops})
        destination = entry_point({"stops": current.stops})
        if origin is None or destination is None:
            continue
        jobs.append((previous, current, origin, destination))

    def run(job):
        previous, current, origin, destination = job
        return build_leg(origin, destination, day, _departure_minute(previous), budget, transit_budget)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, jobs))
    return [
        {"from_item_id": previous.id, "to_item_id": current.id, **leg}
        for (previous, current, _, _), leg in zip(jobs, results)
        if leg is not None
    ]
