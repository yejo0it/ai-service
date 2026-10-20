"""
실제 이동 시간 기준 방문 순서 계산 (AI의 일정 판단과 분리된 서버 계산).

AI는 어떤 장소를 어느 날에 넣을지, 체류 시간(stay_minutes)과 식사 시간대 같은 '판단'만 한다.
이동 시간·교통수단은 Google Routes API 결과만 쓰고, 순서와 도착 시각은 여기서 계산한다.

- 순서: 하루 안에서 새로 넣거나 옮기는 장소(시간이 정해지지 않은 것)를 이동 시간이 가장 짧은 자리에 넣는다.
  이미 있는 일정·시간이 정해진 일정은 그 순서를 지킨다(시작·끝에 고정된 항공·숙소 카드도 그대로).
- 구간 교통수단: 도보(20분 이내면 우선) · 대중교통(환승·대기 부담을 비용에 더한다).
  대중교통 정보가 없는 먼 구간은 자동차 이동 시간을 '순서를 고르는 기준'으로만 쓰고 화면에는 표시하지 않는다(택시·차량 표시 안 함).
  화면에 보여주는 시간은 Google이 돌려준 값 그대로이고, 부담 가중치는 순서를 고르는 데만 쓴다.
- 영업시간: 저장된 영업시간 문장(Places 응답)을 읽어 예상 도착 시각이 영업시간 밖이면 순서를 바꿔 피하고, 피할 수 없으면 경고한다.
- 실제 교통 정보를 쓸 수 없으면(키 없음·지원 지역 밖·한도·오류) 순서를 바꾸지 않고(직선거리 기준 배치 그대로) 그 사실을 표시한다.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations, permutations

from . import routes
from . import transit as navitime
from .itinerary_planner import (
    PLACE_KINDS,
    START_LABELS,
    _bounds,
    day_anchor,
    distance_km,
    entry_point,
    exit_point,
)

WALK_PREFERRED_MIN = 20  # 이 시간 이하의 도보는 대중교통보다 우선
WALK_PENALTY = 1.6  # 긴 도보 가중치
TRANSIT_OVERHEAD_MIN = 8  # 대기·환승 부담(순서 비교용, 화면에는 표시하지 않음)
DRIVE_OVERHEAD_MIN = 5
UNKNOWN_LEG_BASE_MIN = 25  # 이동 정보가 없는 구간의 순서 비교용 비용
UNKNOWN_LEG_PER_KM = 10
VIOLATION_PENALTY = 500
LATE_PENALTY = 8
WAIT_PENALTY = 2
DAY_START_MIN = 9 * 60
CLOSING_BUFFER_MIN = 20
MAX_EXHAUSTIVE = 8  # 장소(고정+이동 가능) 수가 이 이하면 모든 순서를 비교한다
DEFAULT_STAY = {"sight": 90, "restaurant": 60, "cafe": 40}
MIN_STAY, MAX_STAY = 10, 240

# --------------------------------------------------------------------------- #
# 영업시간 문장 읽기 (Places 응답, 한국어)
# --------------------------------------------------------------------------- #

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
_TIME = re.compile(r"(오전|오후)?\s*(\d{1,2}):(\d{2})")


def _clean(text):
    text = re.sub(r"[    ]", " ", text)
    return re.sub(r"[–—~∼]", "~", text)


def _minutes(hour, minute, marker):
    if marker == "오후" and hour < 12:
        hour += 12
    elif marker == "오전" and hour == 12:
        hour = 0
    return hour * 60 + minute


def _parse_range(text):
    """'오전 9:00~오후 6:00' / '09:00~18:00' -> (시작분, 끝분). 해석할 수 없으면 None."""
    parts = text.split("~")
    if len(parts) != 2:
        return None
    start, end = _TIME.search(parts[0]), _TIME.search(parts[1])
    if not start or not end:
        return None
    start_marker, end_marker = start.group(1), end.group(1)
    start_h, start_m = int(start.group(2)), int(start.group(3))
    end_h, end_m = int(end.group(2)), int(end.group(3))
    if not start_marker and end_marker:
        # '11:00~오후 3:00'처럼 앞쪽 표기가 빠졌으면, 끝이 시작보다 늦도록 같은 쪽(오전/오후)으로 읽는다.
        start_marker = end_marker if _minutes(start_h, start_m, end_marker) <= _minutes(end_h, end_m, end_marker) else "오전"
    if not end_marker and start_marker:
        end_marker = start_marker
        if _minutes(end_h, end_m, end_marker) <= _minutes(start_h, start_m, start_marker):
            end_marker = "오후" if start_marker == "오전" else start_marker
    start_min = _minutes(start_h, start_m, start_marker)
    end_min = _minutes(end_h, end_m, end_marker)
    if end_min <= start_min:
        end_min += 24 * 60  # 자정을 넘겨 영업
    return start_min, end_min


def parse_opening_hours(lines, weekday):
    """
    영업시간 문장 목록에서 weekday(월=0)의 영업 구간을 읽는다.
    돌려주는 값: [(시작분, 끝분), ...] · [] (휴무) · None(알 수 없음: 검사하지 않는다)
    """
    prefix = WEEKDAYS[weekday] + "요일"
    for line in lines or []:
        text = _clean(str(line)).strip()
        if not text.startswith(prefix):
            continue
        body = text.split(":", 1)[1].strip() if ":" in text else ""
        if "24시간" in body:
            return [(0, 24 * 60)]
        if "휴무" in body or "휴업" in body:
            return []
        ranges = []
        for chunk in body.split(","):
            parsed = _parse_range(chunk)
            if parsed is None:
                return None
            ranges.append(parsed)
        return ranges or None
    return None


def format_minutes(value):
    value %= 24 * 60
    return f"{value // 60:02d}:{value % 60:02d}"


# --------------------------------------------------------------------------- #
# 구간 비용
# --------------------------------------------------------------------------- #


@dataclass
class LegChoice:
    mode: str  # walk | transit | drive
    seconds: int
    meters: int
    known: bool = True
    cost: float = 0.0  # 순서 비교용(분)
    transfers: int = 0  # 대중교통 환승 횟수(NAVITIME 응답이 있을 때)


class LegTable:
    """한 날의 지점들 사이 구간별 최적 교통수단(도보·대중교통·보조 자동차)."""

    def __init__(self, points, walk, transit, drive):
        self.index = {self._key(p): i for i, p in enumerate(points)}
        self.points = points
        self.walk, self.transit, self.drive = walk, transit, drive
        self._memo = {}

    @staticmethod
    def _key(point):
        return (round(point[0], 6), round(point[1], 6))

    def override(self, a, b, choice):
        """최종 순서의 구간에 NAVITIME 대중교통 결과를 반영한다(순서를 정한 뒤에 쓴다)."""
        self._memo[(self._key(a), self._key(b))] = choice

    def leg(self, a, b):
        key = (self._key(a), self._key(b))
        if key in self._memo:
            return self._memo[key]
        i, j = self.index[key[0]], self.index[key[1]]
        choice = self._choose(i, j, a, b)
        self._memo[key] = choice
        return choice

    def _choose(self, i, j, a, b):
        if i == j:
            return LegChoice("walk", 0, 0, True, 0.0)
        walk, transit, drive = self.walk.get((i, j)), self.transit.get((i, j)), self.drive.get((i, j))
        options = []
        if walk:
            minutes = walk.seconds / 60
            options.append(("walk", walk, minutes if minutes <= WALK_PREFERRED_MIN else minutes * WALK_PENALTY))
        if transit:
            options.append(("transit", transit, transit.seconds / 60 + TRANSIT_OVERHEAD_MIN))
        if not transit and drive and (not walk or walk.seconds > WALK_PREFERRED_MIN * 60):
            options.append(("drive", drive, drive.seconds / 60 + DRIVE_OVERHEAD_MIN))
        if not options:
            km = distance_km(a, b)
            return LegChoice("unknown", 0, int(km * 1000), False, UNKNOWN_LEG_BASE_MIN + km * UNKNOWN_LEG_PER_KM)
        mode, leg, cost = min(options, key=lambda option: option[2])
        return LegChoice(mode, leg.seconds, leg.meters, True, cost)


# --------------------------------------------------------------------------- #
# 하루 시뮬레이션
# --------------------------------------------------------------------------- #


def stay_minutes(card):
    value = card.get("stay_minutes")
    if isinstance(value, int) and value > 0:
        return max(MIN_STAY, min(MAX_STAY, value))
    return DEFAULT_STAY.get(card.get("kind"), 0)


def _time_minutes(value):
    if not value:
        return None
    hour, minute = value.split(":")[:2]
    return int(hour) * 60 + int(minute)


def card_key(card):
    return card.get("_key") or str(card["id"])


@dataclass
class Simulation:
    cost: float
    etas: dict = field(default_factory=dict)  # 카드 키 -> 예상 도착(분)
    warnings: list = field(default_factory=list)
    violations: int = 0


def simulate(day, head, middle, tail, anchor, table):
    """head + middle + tail 순서로 하루를 따라가며 이동 비용·예상 도착·영업시간/시간 충돌을 계산한다."""
    cursor = DAY_START_MIN
    prev = anchor
    for card in head:
        t = _time_minutes(card.get("time"))
        if t is not None:
            cursor = max(cursor, t + 30)
        prev = exit_point(card) or prev
    sim = Simulation(0.0)
    for card in middle + tail:
        entry = entry_point(card)
        arrival = cursor
        if entry and prev:
            leg = table.leg(prev, entry)
            sim.cost += leg.cost
            arrival = cursor + (leg.seconds // 60 if leg.known else round(leg.cost))
        target = _time_minutes(card.get("time"))
        start = arrival
        if target is not None:
            if arrival > target + 5:
                late = arrival - target
                sim.cost += LATE_PENALTY * late
                sim.violations += 1
                sim.warnings.append(f"{card['title']}: 예상 도착({format_minutes(arrival)})이 정한 시간({card['time']})보다 늦어요.")
            start = max(arrival, target)
        if card.get("kind") in PLACE_KINDS:
            hours = card.get("_hours")
            if hours is not None:
                span = next((r for r in hours if start < r[1] - CLOSING_BUFFER_MIN), None)
                if span is None:
                    sim.cost += VIOLATION_PENALTY
                    sim.violations += 1
                    label = "휴무" if not hours else "·".join(f"{format_minutes(a)}~{format_minutes(b)}" for a, b in hours)
                    sim.warnings.append(f"{card['title']}: 영업시간 밖일 수 있어요(예상 도착 {format_minutes(start)}, 영업 {label}).")
                elif start < span[0]:
                    sim.cost += WAIT_PENALTY * (span[0] - start)
                    start = span[0]
        sim.etas[card_key(card)] = start
        cursor = start + stay_minutes(card)
        prev = exit_point(card) or prev
    return sim


def _interleavings(pinned, free_order):
    """고정 카드의 순서를 지키면서 free_order(이동 가능 카드)를 끼워 넣는 모든 배치."""
    total = len(pinned) + len(free_order)
    for slots in combinations(range(total), len(pinned)):
        sequence, pinned_iter, free_iter = [], iter(pinned), iter(free_order)
        slot_set = set(slots)
        for position in range(total):
            sequence.append(next(pinned_iter) if position in slot_set else next(free_iter))
        yield sequence


def best_sequence(day, head, pinned, free, tail, anchor, table):
    """이동 가능한 카드(free)의 최적 배치를 찾는다. 장소가 많으면 하나씩 가장 좋은 자리에 넣는다(그리디)."""
    if len(pinned) + len(free) <= MAX_EXHAUSTIVE:
        candidates = (seq for perm in permutations(free) for seq in _interleavings(pinned, list(perm)))
        best = None
        for index, sequence in enumerate(candidates):
            sim = simulate(day, head, sequence, tail, anchor, table)
            if best is None or (round(sim.cost, 3), index) < (round(best[0].cost, 3), best[2]):
                best = (sim, sequence, index)
        return best[1], best[0]
    sequence = list(pinned)
    for card in free:
        options = [sequence[:i] + [card] + sequence[i:] for i in range(len(sequence) + 1)]
        sequence = min(options, key=lambda seq: round(simulate(day, head, seq, tail, anchor, table).cost, 3))
    return sequence, simulate(day, head, sequence, tail, anchor, table)


# --------------------------------------------------------------------------- #
# 제안 전체
# --------------------------------------------------------------------------- #


@dataclass
class DayPlan:
    basis: str  # google | partial | straight_line
    legs: list  # cards[i] -> cards[i+1] 구간: {"mode","minutes","meters"} 또는 None
    etas: dict
    warnings: list
    order: list  # 카드 키 순서 (실제 이동 시간으로 정한 날만)


@dataclass
class RoutePlan:
    basis: str  # google | partial | straight_line | none
    note: str
    days: dict  # {date: DayPlan}
    elements_used: int = 0

    @property
    def order(self):
        return {day.isoformat(): plan.order for day, plan in self.days.items() if plan.order}


NOTES = {
    "disabled": "실제 이동 시간 정보를 쓰지 않아 직선거리 기준으로 순서를 정했어요.",
    "area": "이 지역은 아직 실제 이동 시간 계산을 지원하지 않아 직선거리 기준으로 순서를 정했어요.",
    "limit": "경로 계산 한도에 도달해 일부 날짜는 직선거리 기준으로 순서를 정했어요.",
    "error": "실제 이동 시간을 가져오지 못해 일부 날짜는 직선거리 기준으로 순서를 정했어요.",
    "partial": "일부 구간은 이동 정보를 찾지 못했어요(시간 표시 없음).",
}


def _is_free(card):
    return (
        (card.get("moved") or not card.get("id"))
        and not card.get("time")
        and card.get("kind") in PLACE_KINDS
        and entry_point(card) is not None
    )


def _unique_points(cards, anchor):
    points, seen = [], set()
    for point in [anchor] + [p for card in cards for p in (entry_point(card), exit_point(card))]:
        if point is None:
            continue
        key = LegTable._key(point)
        if key not in seen:
            seen.add(key)
            points.append(point)
    return points


def describe_legs(cards, table):
    legs = []
    for current, following in zip(cards, cards[1:]):
        a, b = exit_point(current), entry_point(following)
        if a is None or b is None:
            legs.append(None)
            continue
        leg = table.leg(a, b)
        # 자동차 시간은 순서를 정하는 기준일 뿐 사용자에게 보여주지 않는다. 도보·대중교통 정보가 없으면 '정보 없음'이다.
        if not leg.known or leg.mode == "drive":
            legs.append(None)
        else:
            legs.append({"mode": leg.mode, "minutes": max(1, round(leg.seconds / 60)) if leg.seconds else 0,
                         "meters": leg.meters, "transfers": leg.transfers})
    return legs


def _fill_transit(day, cards, sim, table, transit_budget):
    """
    순서를 정한 뒤, 도보로 표시할 수 없는 구간(대중교통 정보 없음)의 대중교통 시간을 NAVITIME에서 가져와 반영한다.
    호출은 최종 순서의 이어지는 구간만 한다. 반영한 구간이 있으면 True.
    """
    wanted = []
    for current, following in zip(cards, cards[1:]):
        a, b = exit_point(current), entry_point(following)
        if a is None or b is None:
            continue
        leg = table.leg(a, b)
        if leg.known and leg.mode in ("walk", "transit"):
            continue
        eta = sim.etas.get(card_key(current))
        wanted.append((a, b, day, (eta if eta is not None else DAY_START_MIN + 60) + stay_minutes(current)))
    if not wanted:
        return False
    changed = False
    for (a, b, _, _), leg in zip(wanted, navitime.fetch_legs(wanted, transit_budget)):
        if leg is not None:
            table.override(a, b, LegChoice("transit", leg.minutes * 60, leg.meters, True, float(leg.minutes), leg.transfers))
            changed = True
    return changed


def _fetch_tables(day, points, budget):
    """한 날의 도보·대중교통(·필요하면 자동차) 행렬. Routes API를 쓸 수 없으면 RoutesError."""
    departure, bucket = routes.departure_for(day)
    walk = routes.travel_matrix(points, "WALK", budget=budget)
    pairs = [(i, j) for i in range(len(points)) for j in range(len(points)) if i != j]
    need_transit = any(not walk.get(p) or walk[p].seconds > 15 * 60 for p in pairs)
    transit = routes.travel_matrix(points, "TRANSIT", bucket, departure, budget) if need_transit else {}
    need_drive = any(
        not transit.get(p) and (not walk.get(p) or walk[p].seconds > WALK_PREFERRED_MIN * 60) for p in pairs
    )
    drive = routes.travel_matrix(points, "DRIVE", budget=budget) if need_drive else {}
    return walk, transit, drive


def plan_days(trip, days, user_id=None, budget=None, transit_budget=None):
    """
    제안을 반영한 days({date: [card]})에서, 새로 넣거나 옮긴 장소가 있는 날의 순서를 실제 이동 시간 기준으로 다시 정한다.
    days를 직접 바꾸고, 날짜별 구간 정보·예상 도착·경고를 담은 RoutePlan을 돌려준다.
    """
    budget = budget or routes.Budget(user_id)
    transit_budget = transit_budget or navitime.TransitBudget()
    plans, reasons = {}, set()
    for day in sorted(days):
        cards = days[day]
        if not any(_is_free(card) for card in cards):
            continue
        anchor = day_anchor(trip, day, cards)
        lo, hi = _bounds(cards)
        free = [card for index, card in enumerate(cards) if _is_free(card) and lo <= index < hi]
        if not free:
            continue
        for card in cards:  # 영업시간 문장은 한 번만 읽는다(순서를 수천 번 비교하므로)
            card["_hours"] = parse_opening_hours(card.get("opening_hours"), day.weekday())
        points = _unique_points(cards, anchor)
        straight = DayPlan("straight_line", [None] * max(0, len(cards) - 1), {}, [], [])

        if not routes.enabled():
            reasons.add("disabled")
        elif not all(routes.in_service_area(p) for p in points):
            reasons.add("area")
        else:
            try:
                walk, transit, drive = _fetch_tables(day, points, budget)
            except routes.BudgetExceeded:
                reasons.add("limit")
            except routes.RoutesError:
                reasons.add("error")
            else:
                table = LegTable(points, walk, transit, drive)
                head, middle, tail = cards[:lo], cards[lo:hi], cards[hi:]
                pinned = [card for card in middle if not any(card is other for other in free)]
                sequence, sim = best_sequence(day, head, pinned, free, tail, anchor, table)
                days[day] = head + sequence + tail
                if _fill_transit(day, days[day], sim, table, transit_budget):
                    # 대중교통 시간을 반영해 예상 도착과 영업시간 경고를 다시 계산한다(순서는 그대로).
                    sim = simulate(day, head, sequence, tail, anchor, table)
                legs = describe_legs(days[day], table)
                # 순서를 정할 이동 시간 정보(자동차 시간 포함)가 하나라도 있었는지. 표시할 구간이 없어도 순서는 그 정보로 정했다.
                has_data = any(
                    table.leg(exit_point(a), entry_point(b)).known
                    for a, b in zip(days[day], days[day][1:])
                    if exit_point(a) is not None and entry_point(b) is not None
                )
                basis = "google" if all(legs) else ("partial" if has_data else "straight_line")
                if basis == "straight_line":
                    days[day] = cards  # 이동 정보가 전혀 없으면 순서를 바꾸지 않는다
                    plans[day] = straight
                    reasons.add("error")
                    continue
                if basis == "partial":
                    reasons.add("partial")
                plans[day] = DayPlan(basis, legs, sim.etas, sim.warnings, [card_key(c) for c in days[day]])
                continue
        plans[day] = straight
    if not plans:
        return RoutePlan("none", "", {}, budget.used)
    bases = {plan.basis for plan in plans.values()}
    basis = "google" if bases == {"google"} else ("straight_line" if bases == {"straight_line"} else "partial")
    notes = [NOTES[key] for key in ("disabled", "area", "limit", "error", "partial") if key in reasons]
    return RoutePlan(basis, " ".join(notes[:2]), plans, budget.used)


def apply_order(days, order):
    """
    미리보기에서 정한 날짜별 순서(카드 키 목록)를 days에 반영한다. 적용할 때 Routes API를 다시 부르지 않고
    미리본 순서 그대로 저장하기 위해서다. 그날 카드 구성이 미리볼 때와 다르면(그사이 일정이 바뀜) 그 날짜는 건드리지 않는다.
    """
    for raw_day, keys in (order or {}).items():
        try:
            day = date.fromisoformat(raw_day)
        except ValueError:
            continue
        if day not in days or len(set(keys)) != len(keys):
            continue
        by_key = {card_key(card): card for card in days[day] if card.get("id") or card.get("_key")}
        if len(by_key) != len(days[day]) or set(keys) != set(by_key):
            continue
        days[day] = [by_key[key] for key in keys]
