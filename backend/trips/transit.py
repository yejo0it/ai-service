"""
일본 대중교통 이동 시간: NAVITIME Route(totalnavi, RapidAPI).

Google Routes API는 일본(도쿄) 대중교통 경로를 돌려주지 않아서, 대중교통 구간의 시간만 이 서비스에서 가져온다.
- 출발지→도착지 한 건씩 호출하는 API라서(경로 행렬 없음), 방문 순서를 정한 뒤 '최종 순서의 이어지는 구간'만 호출한다.
- 무료 요금제는 월 500건 하드 리밋이다. 제안 한 번의 호출 수, 월 호출 수, 응답 헤더의 남은 횟수로 제한한다.
- 같은 구간은 짧게 캐시한다(DB 저장 없음). 출발 요일(평일/토/일)과 출발 시간대(30분)를 캐시 키에 넣는다.
- 응답이 없거나 경로를 못 찾으면 None이다. 시간을 추정해서 채우지 않는다.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import routes

HOST = "navitime-route-totalnavi.p.rapidapi.com"
NOT_FOUND = "NA"
WORKERS = 4


class TransitBudgetExceeded(Exception):
    """호출 수 상한에 닿았다."""


@dataclass(frozen=True)
class TransitLeg:
    minutes: int
    meters: int
    transfers: int


def api_key():
    return os.environ.get("NAVITIME_RAPIDAPI_KEY", "")


def enabled():
    return bool(api_key()) and settings.NAVITIME_ENABLED


class TransitBudget:
    """제안 한 번의 호출 수 + 월 호출 수. 월 한도 남은 횟수는 응답 헤더로도 확인한다."""

    def __init__(self):
        self.used = 0
        self.left = settings.NAVITIME_MAX_REQUESTS_PER_PROPOSAL
        self._lock = threading.Lock()

    @staticmethod
    def _month_key():
        return f"navitime:month:{timezone.now().strftime('%Y%m')}"

    def take(self):
        with self._lock:
            self._take()

    def _take(self):
        if self.left <= 0:
            raise TransitBudgetExceeded("제안 한 번의 대중교통 호출 한도")
        remaining = cache.get("navitime:remaining")
        if remaining is not None and remaining <= settings.NAVITIME_RESERVE:
            raise TransitBudgetExceeded("대중교통 월 호출 한도")
        key = self._month_key()
        if cache.get(key, 0) >= settings.NAVITIME_MONTHLY_REQUESTS:
            raise TransitBudgetExceeded("대중교통 월 호출 한도")
        cache.add(key, 0, 60 * 60 * 24 * 40)
        cache.incr(key)
        self.left -= 1
        self.used += 1


def _request(origin, destination, start_time):
    """route_transit 한 건. (응답 JSON, 월 남은 호출 수)를 돌려준다."""
    if settings.TESTING:
        return None, None  # 테스트에서는 실제 호출하지 않는다
    query = urllib.parse.urlencode(
        {"start": f"{origin[0]},{origin[1]}", "goal": f"{destination[0]},{destination[1]}", "start_time": start_time}
    )
    request = urllib.request.Request(
        f"https://{HOST}/route_transit?{query}",
        headers={"x-rapidapi-key": api_key(), "x-rapidapi-host": HOST},
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.NAVITIME_TIMEOUT_SECONDS) as response:
            remaining = response.headers.get("X-RateLimit-Requests-Remaining")
            return json.loads(response.read().decode()), int(remaining) if remaining is not None else None
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            cache.set("navitime:remaining", 0, 60 * 60)
        return None, None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None, None


def _parse(payload):
    """응답의 첫 경로(가장 좋은 경로)의 이동 시간(분)·거리(m)·환승 횟수. 경로가 없으면 None."""
    try:
        move = payload["items"][0]["summary"]["move"]
        return TransitLeg(int(move["time"]), int(move.get("distance", 0)), int(move.get("transit_count", 0)))
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _bucket(day, minute):
    daytype = "weekday" if day.weekday() < 5 else ("sat" if day.weekday() == 5 else "sun")
    return f"{daytype}-{minute // 30 * 30:04d}"


def start_time_for(day, minute):
    """시간표 기준 출발 시각(현지, 시간대 없는 ISO). 지난 날·먼 미래는 같은 요일의 가까운 미래 날짜를 대표로 쓴다."""
    target = routes.representative_date(day, country="JP")
    minute = minute // 30 * 30
    return datetime(target.year, target.month, target.day, minute // 60 % 24, minute % 60).isoformat()


def fetch_legs(requests, budget):
    """
    requests: [(origin, destination, 출발 분)] -> 같은 길이의 [TransitLeg 또는 None].
    캐시에 없는 구간만 병렬로 호출한다. 한도에 닿으면 남은 구간은 None(정보 없음)이다.
    """
    if not enabled():
        return [None] * len(requests)
    results = [None] * len(requests)
    pending = []
    for index, (origin, destination, day, minute) in enumerate(requests):
        key = f"navitime:{origin[0]:.5f},{origin[1]:.5f}:{destination[0]:.5f},{destination[1]:.5f}:{_bucket(day, minute)}"
        hit = cache.get(key)
        if hit is not None:
            results[index] = None if hit == NOT_FOUND else TransitLeg(*hit)
            continue
        try:
            budget.take()
        except TransitBudgetExceeded:
            break
        pending.append((index, key, origin, destination, start_time_for(day, minute)))

    def run(item):
        _, _, origin, destination, start_time = item
        return _request(origin, destination, start_time)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        responses = list(pool.map(run, pending))
    for (index, key, *_), (payload, remaining) in zip(pending, responses):
        if remaining is not None:
            cache.set("navitime:remaining", remaining, 60 * 60 * 24)
        if payload is None:
            continue  # 호출 실패는 캐시하지 않는다(잠깐의 오류일 수 있다)
        leg = _parse(payload)
        results[index] = leg
        cache.set(key, NOT_FOUND if leg is None else (leg.minutes, leg.meters, leg.transfers), settings.ROUTES_CACHE_TTL_SECONDS)
    return results
