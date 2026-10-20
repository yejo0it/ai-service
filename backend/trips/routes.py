"""
Google Routes API(경로 행렬)로 장소 사이의 실제 이동 시간·거리를 가져온다.

- 교통수단은 도보(WALK)·대중교통(TRANSIT)이 기본이고, 대중교통 정보가 없는 구간에만 자동차(DRIVE, 택시 가정)를 보조로 쓴다.
  Google이 경로를 찾지 못한 구간은 None으로 돌려주며, 이동 시간을 추정해서 채우지 않는다.
- 서비스 지역은 설정(ROUTES_COUNTRIES·ROUTES_CITIES, 기본 동아시아)으로 제한한다. 일본 대중교통은 Google이 주지 않아 trips.transit(NAVITIME)이
  맡고, 그 밖의 나라는 Google 대중교통 결과를 쓴다. 지원 지역을 확인한 뒤 점차 넓힌다.
- 비용 제한: 한 번의 제안 / 사용자별 하루 / 전체 하루 요소 수 상한(Budget), 같은 쌍은 캐시해서 다시 부르지 않는다.
  교통량·혼잡 반영 옵션(TRAFFIC_AWARE)은 쓰지 않는다(더 비싼 등급이므로).
- 캐시 정책: Google Maps 콘텐츠를 DB에 저장하지 않고, 짧은 유효 시간(기본 6시간)의 서버 메모리 캐시에만 둔다.
  대중교통은 출발 요일(평일/토/일)·시간대를 캐시 키에 넣어, 다른 시간대의 결과를 재사용하지 않는다.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
import threading
from datetime import datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import cities

ROUTES_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
# 이동 시간·거리·경로 유무만 받는다(교통량 반영 필드·경로선은 받지 않는다).
FIELD_MASK = "originIndex,destinationIndex,duration,distanceMeters,condition,status"
NOT_FOUND = "NA"  # 캐시에 두는 '경로 없음' 표시
DEPARTURE_HOUR = 11  # 대중교통 대표 출발 시각(현지)


class RoutesError(Exception):
    """Routes API를 쓸 수 없는 경우(키 없음·오류·시간 초과)."""


class BudgetExceeded(RoutesError):
    """요청 수 상한을 넘은 경우."""


@dataclass(frozen=True)
class Leg:
    mode: str  # WALK | TRANSIT | DRIVE
    seconds: int
    meters: int


def api_key():
    return os.environ.get("GOOGLE_ROUTES_API_KEY", "")


def enabled():
    return bool(api_key()) and settings.ROUTES_ENABLED


# 나라별 시간대(대중교통 시간표 조회 날짜·시각 계산용). 없으면 ROUTES_TIMEZONE.
TIMEZONES = {
    "JP": "Asia/Tokyo", "KR": "Asia/Seoul", "TW": "Asia/Taipei", "HK": "Asia/Hong_Kong",
    "MO": "Asia/Macau", "CN": "Asia/Shanghai", "MN": "Asia/Ulaanbaatar",
}


@lru_cache(maxsize=8)
def _centers(countries, city_ids):
    return tuple(
        (city["lat"], city["lng"], city["country"])
        for city in cities.all_cities()
        if city["country"] in countries or city["id"] in city_ids
    )


def service_area(point):
    """
    point(lat, lng)가 서비스 지역(설정한 나라·도시의 도시 중심 주변 ROUTES_CITY_RADIUS_KM 이내)이면 그 나라 코드, 아니면 None.
    """
    from .itinerary_planner import distance_km

    centers = _centers(tuple(settings.ROUTES_COUNTRIES), tuple(settings.ROUTES_CITIES))
    nearest = min(((distance_km((lat, lng), point), country) for lat, lng, country in centers), default=None)
    return nearest[1] if nearest and nearest[0] <= settings.ROUTES_CITY_RADIUS_KM else None


def in_service_area(point):
    return service_area(point) is not None


class Budget:
    """요소(출발지×도착지 쌍) 수 상한: 제안 한 번 · 사용자별 하루 · 전체 하루."""

    def __init__(self, user_id=None):
        self.user_id = user_id
        self.left = settings.ROUTES_MAX_ELEMENTS_PER_PROPOSAL
        self.used = 0
        self._lock = threading.Lock()  # 구간을 병렬로 계산해도 한도를 정확히 센다

    @staticmethod
    def _day():
        return timezone.now().strftime("%Y%m%d")

    def _counters(self):
        counters = [(f"routes:elements:all:{self._day()}", settings.ROUTES_DAILY_ELEMENTS)]
        if self.user_id is not None:
            counters.append((f"routes:elements:user:{self.user_id}:{self._day()}", settings.ROUTES_USER_DAILY_ELEMENTS))
        return counters

    def take(self, count):
        with self._lock:
            self._take(count)

    def _take(self, count):
        if count > self.left:
            raise BudgetExceeded("제안 한 번에 쓸 수 있는 경로 계산 한도를 넘었어요.")
        counters = self._counters()
        for key, limit in counters:
            if cache.get(key, 0) + count > limit:
                raise BudgetExceeded("오늘 경로 계산 한도를 넘었어요.")
        for key, _ in counters:
            cache.add(key, 0, 60 * 60 * 26)
            cache.incr(key, count)
        self.left -= count
        self.used += count


def _zone(country=None):
    return ZoneInfo(TIMEZONES.get(country) or settings.ROUTES_TIMEZONE)


def representative_date(day, now=None, country=None):
    """
    시간표 조회에 쓸 날짜(현지). 지난 날이나 너무 먼 미래는 조회할 수 없으므로 같은 요일의 가장 가까운 미래 날짜를 대표로 쓴다.
    (공휴일은 구분하지 않는다)
    """
    tz = _zone(country)
    local_now = (now or timezone.now()).astimezone(tz)
    candidate = datetime.combine(day, time(DEPARTURE_HOUR, 0), tz)
    if candidate > local_now + timedelta(hours=1) and candidate <= local_now + timedelta(days=settings.ROUTES_MAX_FUTURE_DAYS):
        return day
    target = local_now.date() + timedelta(days=1)
    while target.weekday() != day.weekday():
        target += timedelta(days=1)
    return target


def departure_for(day, now=None, country=None):
    """
    대중교통 출발 시각(RFC 3339, UTC)과 캐시용 시간대 이름.
    Google은 과거·너무 먼 미래의 출발 시각을 받지 않으므로 representative_date로 대표 날짜를 쓴다.
    """
    tz = _zone(country)
    target = representative_date(day, now, country)
    candidate = datetime.combine(target, time(DEPARTURE_HOUR, 0), tz)
    daytype = "weekday" if day.weekday() < 5 else ("sat" if day.weekday() == 5 else "sun")
    return candidate.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), f"{daytype}-{DEPARTURE_HOUR}h"


def _waypoint(point):
    return {"waypoint": {"location": {"latLng": {"latitude": point[0], "longitude": point[1]}}}}


def _send(url, body, field_mask):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": api_key(), "X-Goog-FieldMask": field_mask},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.ROUTES_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RoutesError(f"Routes API 오류({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise RoutesError("Routes API를 호출하지 못했어요.") from exc


def _post(body):
    """computeRouteMatrix 호출. 응답은 요소 목록(JSON 배열)이다."""
    if settings.TESTING:
        raise RoutesError("테스트에서는 실제 호출하지 않아요.")
    return _send(ROUTES_URL, body, FIELD_MASK)


DIRECTIONS_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
# 대중교통 구간 표시에 필요한 필드만 받는다(요금·경로선·교통량 필드는 받지 않는다).
DIRECTIONS_FIELDS = ",".join(
    (
        "routes.duration",
        "routes.distanceMeters",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.transitDetails.stopDetails.departureStop.name",
        "routes.legs.steps.transitDetails.stopDetails.arrivalStop.name",
        "routes.legs.steps.transitDetails.stopDetails.departureTime",
        "routes.legs.steps.transitDetails.stopDetails.arrivalTime",
        "routes.legs.steps.transitDetails.transitLine.name",
        "routes.legs.steps.transitDetails.transitLine.nameShort",
        "routes.legs.steps.transitDetails.transitLine.color",
        "routes.legs.steps.transitDetails.stopCount",
    )
)


def _post_directions(body):
    if settings.TESTING:
        raise RoutesError("테스트에서는 실제 호출하지 않아요.")
    return _send(DIRECTIONS_URL, body, DIRECTIONS_FIELDS)


def compute_transit_route(origin, destination, day, depart_minute, country=None, budget=None):
    """
    origin→destination 대중교통 경로 한 건(노선·승하차 정류장·시각). 응답 JSON을 그대로 돌려준다(해석은 trips.legs).
    출발 시각은 representative_date의 현지 날짜 + depart_minute(분)다.
    """
    if not enabled():
        raise RoutesError("Routes API를 쓸 수 없어요.")
    if budget is not None:
        budget.take(1)
    tz = _zone(country)
    target = representative_date(day, country=country)
    local = datetime.combine(target, time(depart_minute // 60 % 24, depart_minute % 60), tz)
    body = {
        "origin": _waypoint(origin)["waypoint"],
        "destination": _waypoint(destination)["waypoint"],
        "travelMode": "TRANSIT",
        "departureTime": local.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "languageCode": "ko",
    }
    return _post_directions(body)


def _cache_key(mode, origin, destination, bucket):
    return f"routes:{mode}:{origin[0]:.5f},{origin[1]:.5f}:{destination[0]:.5f},{destination[1]:.5f}:{bucket}"


def _parse_seconds(value):
    try:
        return int(float(str(value).rstrip("s")))
    except (TypeError, ValueError):
        return None


def travel_matrix(points, mode, bucket="any", departure=None, budget=None):
    """
    points(lat, lng 목록) 사이의 이동 정보: {(i, j): Leg 또는 None}. None은 Google이 경로를 찾지 못한 구간이다.
    캐시에 있는 쌍은 다시 부르지 않고, 없는 쌍만 한 번의 요청으로 가져온다.
    """
    result = {}
    missing = []
    keys = {}
    for i, origin in enumerate(points):
        for j, destination in enumerate(points):
            if i == j:
                result[(i, j)] = Leg(mode, 0, 0)
                continue
            keys[(i, j)] = _cache_key(mode, origin, destination, bucket)
    cached = cache.get_many(list(keys.values()))
    for pair, key in keys.items():
        if key in cached:
            value = cached[key]
            result[pair] = None if value == NOT_FOUND else Leg(mode, *value)
        else:
            missing.append(pair)
    if not missing:
        return result
    if not enabled():
        raise RoutesError("Routes API를 쓸 수 없어요.")

    origins = sorted({i for i, _ in missing})
    destinations = sorted({j for _, j in missing})
    if budget is not None:
        budget.take(len(origins) * len(destinations))
    body = {
        "origins": [_waypoint(points[i]) for i in origins],
        "destinations": [_waypoint(points[j]) for j in destinations],
        "travelMode": mode,
    }
    if mode == "TRANSIT" and departure:
        body["departureTime"] = departure
    elements = _post(body)
    if not isinstance(elements, list):
        raise RoutesError("Routes API 응답을 해석하지 못했어요.")

    fresh = {}
    for element in elements:
        # 값이 0이면 응답에서 빠지므로 기본값은 0이다.
        i = origins[element.get("originIndex", 0)]
        j = destinations[element.get("destinationIndex", 0)]
        if i == j:
            continue  # 같은 지점은 이동 없음
        seconds = _parse_seconds(element.get("duration"))
        found = element.get("condition") != "ROUTE_NOT_FOUND" and not element.get("status", {}).get("code") and seconds is not None
        leg = Leg(mode, seconds, int(element.get("distanceMeters", 0))) if found else None
        result[(i, j)] = leg
        if i != j:
            fresh[_cache_key(mode, points[i], points[j], bucket)] = NOT_FOUND if leg is None else (leg.seconds, leg.meters)
    cache.set_many(fresh, timeout=settings.ROUTES_CACHE_TTL_SECONDS)
    for pair in missing:
        result.setdefault(pair, None)
    return result
