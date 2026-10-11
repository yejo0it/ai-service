"""
일정 배치: 새 장소를 어느 날, 그날의 어느 자리에 넣을지 정한다(직선거리 기준).

- 날짜를 정하지 않은 장소는 그날 묵는 숙소(없으면 그날 일정의 중심, 그것도 없으면 여행 도시)에서
  가장 가까운 날로 보낸다. 하루 장소 수에는 상한을 둔다(출국·귀국일은 더 적게).
- 하루 안에서는 시작 고정 카드(출국편·체크아웃·숙박) 뒤, 끝 고정 카드(체크인·귀국편) 앞 사이에 넣는다.
  - 시간을 정한 장소: 시간 순서에 맞는 자리
  - 시간이 없는 장소: 앞뒤 일정 사이 이동 거리가 가장 적게 늘어나는 자리
- 실제 이동 시간이 아니라 직선거리(하버사인)로 계산한다(추가 API 비용 없음).

일정 카드는 dict로 다룬다: {"kind", "time"("HH:MM" 또는 ""), "time_label", "stops": [{"lat", "lng"}...]}
"""

import math
from datetime import date

from . import cities

# 시작·끝에 고정되는 카드 (time_label 기준)
START_LABELS = {"출국", "체크아웃", "숙박"}
END_LABELS = {"체크인", "귀국"}
PLACE_KINDS = {"sight", "restaurant", "cafe"}
MAX_PLACES_PER_DAY = 5
MAX_PLACES_FLIGHT_DAY = 3


def distance_km(a, b):
    """두 (lat, lng) 사이 직선거리(km)."""
    lat1, lng1 = map(math.radians, a)
    lat2, lng2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _located(stops):
    return [(s["lat"], s["lng"]) for s in stops if s.get("lat") is not None and s.get("lng") is not None]


def entry_point(card):
    """카드에 들어가는 위치 (항공편이면 출발 공항)"""
    points = _located(card.get("stops", []))
    return points[0] if points else None


def exit_point(card):
    """카드에서 나오는 위치 (항공편이면 도착 공항)"""
    points = _located(card.get("stops", []))
    return points[-1] if points else None


def _bounds(cards):
    """새 장소를 넣을 수 있는 인덱스 범위 [lo, hi]"""
    lo = 0
    for index, card in enumerate(cards):
        if card.get("time_label") in START_LABELS:
            lo = index + 1
    hi = len(cards)
    for index, card in enumerate(cards):
        if index >= lo and card.get("time_label") in END_LABELS:
            hi = index
            break
    return lo, max(lo, hi)


def insert_index(cards, point, time="", day_anchor=None):
    """cards(그날 순서) 안에서 새 장소(point, time)를 넣을 인덱스."""
    lo, hi = _bounds(cards)
    if time:
        # 시간을 정한 일정들 사이에서 시간 순서가 맞는 자리
        timed = [i for i in range(lo, hi) if cards[i].get("time")]
        after = [i for i in timed if cards[i]["time"] <= time]
        before = [i for i in timed if cards[i]["time"] > time]
        if after:
            return after[-1] + 1
        if before:
            return before[0]
    if point is None:
        return hi

    def cost(index):
        prev = next((exit_point(cards[i]) for i in range(index - 1, -1, -1) if exit_point(cards[i])), day_anchor)
        nxt = next((entry_point(cards[i]) for i in range(index, len(cards)) if entry_point(cards[i])), None)
        added = (distance_km(prev, point) if prev else 0) + (distance_km(point, nxt) if nxt else 0)
        if prev and nxt:
            added -= distance_km(prev, nxt)
        return added

    return min(range(lo, hi + 1), key=lambda index: (round(cost(index), 3), index))


def day_anchor(trip, day, cards):
    """
    그날의 기준 위치: 그날 밤 묵는 숙소 → 그날 아침 체크아웃하는 숙소 → 그날 일정의 중심 → 첫 여행 도시
    (마지막 날처럼 묵는 숙소가 없는 날은 아침에 머문 곳을 기준으로 한다)
    """
    hotels = [h for h in trip.hotels.all() if h.latitude is not None and h.longitude is not None]
    for hotel in hotels:
        if hotel.check_in <= day and (hotel.check_out is None or day < hotel.check_out):
            return (hotel.latitude, hotel.longitude)
    for hotel in hotels:
        if hotel.check_out == day:
            return (hotel.latitude, hotel.longitude)
    points = [p for card in cards for p in _located(card.get("stops", []))]
    if points:
        return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    return cities.trip_center(trip)


def _capacity(cards):
    has_flight = any(card.get("kind") == "flight" for card in cards)
    return MAX_PLACES_FLIGHT_DAY if has_flight else MAX_PLACES_PER_DAY


def choose_day(trip, days, point):
    """
    날짜를 정하지 않은 장소의 날짜. days: {date: [cards]}.
    자리가 남은 날 중 기준 위치가 가장 가까운 날, 모두 찼으면 가장 가까운 날.
    """
    def score(day):
        anchor = day_anchor(trip, day, days[day])
        return distance_km(anchor, point) if anchor and point else 0

    open_days = [d for d in sorted(days) if sum(c.get("kind") in PLACE_KINDS for c in days[d]) < _capacity(days[d])]
    candidates = open_days or sorted(days)
    return min(candidates, key=lambda d: (round(score(d), 3), d))


def place_cards(trip, days, additions):
    """
    days({date: [cards]})에 additions를 배치한다. 각 addition은 card dict에 선택적으로
    "day"(date)를 가진다. 시간을 정한 장소를 먼저, 나머지는 받은 순서대로 넣는다.
    days를 직접 바꾸고, 각 addition이 들어간 날짜를 돌려준다.
    """
    placed = []
    ordered = sorted(additions, key=lambda card: 0 if card.get("time") else 1)
    for card in ordered:
        point = entry_point(card)
        day = card.get("day")
        if day not in days:
            day = choose_day(trip, days, point)
        cards = days[day]
        anchor = day_anchor(trip, day, cards)
        cards.insert(insert_index(cards, point, card.get("time", ""), anchor), card)
        placed.append(day)
    return placed


def trip_days(trip):
    """여행 기간의 날짜 목록"""
    total = (trip.end_date - trip.start_date).days
    return [date.fromordinal(trip.start_date.toordinal() + i) for i in range(total + 1)]
