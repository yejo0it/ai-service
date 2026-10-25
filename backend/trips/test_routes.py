"""
실제 이동 시간 기반 방문 순서 테스트 (Google Routes API는 모두 모킹한다).
- 영업시간 문장 해석
- 경로 행렬: 캐시·한도·경로 없음 처리
- 순서: 직선거리가 아니라 이동 시간으로 정한다 / 영업시간·시간 충돌 / 이동 정보가 없으면 임의로 만들지 않는다
- 제안 → 적용: 미리본 순서가 그대로 저장되고, 적용할 때 Routes API를 다시 부르지 않는다
"""

from datetime import date, datetime, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from . import ai_planner, route_planner, routes, transit
from .models import Hotel, ItineraryItem, Trip

User = get_user_model()
TOKYO_STATION = (35.6812, 139.7671)
HOTEL = (35.6895, 139.6917)  # 신주쿠


def card(title, point, kind="sight", **extra):
    return {"kind": kind, "title": title, "time": "", "time_label": "", "stops": [{"lat": point[0], "lng": point[1]}],
            "opening_hours": [], **extra}


class OpeningHoursTests(SimpleTestCase):
    def hours(self, lines, weekday=0):
        return route_planner.parse_opening_hours(lines, weekday)

    def test_korean_12_hour_ranges(self):
        self.assertEqual(self.hours(["월요일: 오전 9:00~오후 6:00"]), [(540, 1080)])
        self.assertEqual(self.hours(["월요일: 오전 11:00~오후 3:00, 오후 5:00~10:00"]), [(660, 900), (1020, 1320)])
        self.assertEqual(self.hours(["월요일: 오전 9:00 – 오후 6:00"]), [(540, 1080)])  # 이음표·좁은 공백

    def test_24_hour_style_closed_all_day_and_unknown(self):
        self.assertEqual(self.hours(["월요일: 09:00~18:00"]), [(540, 1080)])
        self.assertEqual(self.hours(["월요일: 24시간 영업"]), [(0, 1440)])
        self.assertEqual(self.hours(["월요일: 휴무일"]), [])
        self.assertIsNone(self.hours(["월요일: 예약 필수"]))  # 해석할 수 없으면 검사하지 않는다
        self.assertIsNone(self.hours([]))
        self.assertIsNone(self.hours(["화요일: 09:00~18:00"], weekday=0))  # 그 요일 정보 없음

    def test_past_midnight(self):
        self.assertEqual(self.hours(["금요일: 오후 6:00~오전 2:00"], weekday=4), [(1080, 1560)])


class MatrixTests(TestCase):
    def setUp(self):
        cache.clear()
        self.points = [(35.68, 139.70), (35.69, 139.71), (35.70, 139.72)]

    def elements(self, mode_seconds):
        """모든 (i, j) 쌍에 대한 응답 요소. 0 값은 Google처럼 필드를 생략한다."""
        out = []
        for i in range(3):
            for j in range(3):
                element = {"duration": f"{mode_seconds}s", "distanceMeters": 1000, "condition": "ROUTE_EXISTS"}
                if i:
                    element["originIndex"] = i
                if j:
                    element["destinationIndex"] = j
                out.append(element)
        return out

    @override_settings()
    def test_second_call_uses_cache_and_budget_counts_elements(self):
        budget = routes.Budget(user_id=1)
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), \
                mock.patch("trips.routes._post", return_value=self.elements(600)) as post:
            first = routes.travel_matrix(self.points, "WALK", budget=budget)
            second = routes.travel_matrix(self.points, "WALK", budget=budget)
        self.assertEqual(post.call_count, 1)  # 같은 쌍은 다시 부르지 않는다
        self.assertEqual(first[(0, 1)], routes.Leg("WALK", 600, 1000))
        self.assertEqual(second, first)
        self.assertEqual(budget.used, 9)  # 3 x 3 요소

    def test_cache_key_separates_transit_departure_buckets(self):
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), \
                mock.patch("trips.routes._post", return_value=self.elements(900)) as post:
            routes.travel_matrix(self.points, "TRANSIT", "weekday-11h", "2030-01-01T02:00:00Z")
            routes.travel_matrix(self.points, "TRANSIT", "weekday-11h", "2030-01-01T02:00:00Z")
            routes.travel_matrix(self.points, "TRANSIT", "sun-11h", "2030-01-06T02:00:00Z")  # 다른 시간대는 다시 부른다
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0].args[0]["departureTime"], "2030-01-01T02:00:00Z")

    def test_no_route_is_none_not_estimated(self):
        elements = self.elements(600)
        elements[1] = {"originIndex": 0, "destinationIndex": 1, "condition": "ROUTE_NOT_FOUND"}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), mock.patch("trips.routes._post", return_value=elements):
            matrix = routes.travel_matrix(self.points, "TRANSIT", "weekday-11h", None)
        self.assertIsNone(matrix[(0, 1)])
        self.assertIsNotNone(matrix[(0, 2)])
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), mock.patch("trips.routes._post") as post:
            routes.travel_matrix(self.points, "TRANSIT", "weekday-11h", None)
        post.assert_not_called()  # 경로 없음도 캐시한다

    @override_settings(ROUTES_MAX_ELEMENTS_PER_PROPOSAL=5)
    def test_proposal_limit(self):
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), mock.patch("trips.routes._post") as post:
            with self.assertRaises(routes.BudgetExceeded):
                routes.travel_matrix(self.points, "WALK", budget=routes.Budget(1))
        post.assert_not_called()

    @override_settings(ROUTES_USER_DAILY_ELEMENTS=10)
    def test_user_daily_limit(self):
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), mock.patch("trips.routes._post", return_value=self.elements(60)):
            routes.travel_matrix(self.points, "WALK", budget=routes.Budget(7))  # 9
            cache.clear_cached = None
            other = [(36.0, 140.0), (36.1, 140.1), (36.2, 140.2)]
            with self.assertRaises(routes.BudgetExceeded):
                routes.travel_matrix(other, "WALK", budget=routes.Budget(7))  # 9 + 9 > 10
            routes.travel_matrix(other, "WALK", budget=routes.Budget(8))  # 다른 사용자는 별도

    def test_no_key_raises(self):
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": ""}):
            with self.assertRaises(routes.RoutesError):
                routes.travel_matrix(self.points, "WALK")

    def test_departure_uses_future_time_for_past_days(self):
        now = datetime(2026, 10, 15, 3, 0, tzinfo=dt_timezone.utc)  # 일본 12시
        value, bucket = routes.departure_for(date(2026, 10, 12), now=now)  # 지난 월요일 -> 다음 월요일 11시(KST)
        self.assertEqual((value, bucket), ("2026-10-19T02:00:00Z", "weekday-11h"))
        value, bucket = routes.departure_for(date(2026, 10, 17), now=now)  # 가까운 토요일은 그날
        self.assertEqual((value, bucket), ("2026-10-17T02:00:00Z", "sat-11h"))


def matrix_from(durations, points, mode="TRANSIT"):
    """{(i, j): 초} -> {(i, j): Leg}. 없는 쌍은 None."""
    n = len(points)
    return {(i, j): (routes.Leg(mode, durations[(i, j)], durations[(i, j)] * 1) if (i, j) in durations else None)
            for i in range(n) for j in range(n) if i != j} | {(i, i): routes.Leg(mode, 0, 0) for i in range(n)}


class OrderingTests(TestCase):
    """직선거리가 가까워도 이동 시간이 오래 걸리면 피한다."""

    def setUp(self):
        cache.clear()
        owner = User.objects.create_user(username="o@example.com")
        self.trip = Trip.objects.create(owner=owner, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2030-01-07", end_date="2030-01-08", itinerary_initialized=True)
        Hotel.objects.create(trip=self.trip, name="신주쿠 호텔", address="", latitude=HOTEL[0], longitude=HOTEL[1],
                             check_in="2030-01-07", check_out="2030-01-09")
        self.day = date(2030, 1, 7)  # 월요일
        # A: 호텔에서 아주 가깝지만 B와는 이동이 오래 걸린다. C는 A에서 가깝다.
        self.a = (35.6900, 139.7000)
        self.b = (35.6905, 139.7010)  # A에서 직선 100m
        self.c = (35.7000, 139.7500)

    def run_plan(self, cards, durations_walk, durations_transit, **extra):
        days = {self.day: cards}
        points = route_planner._unique_points(cards, HOTEL)
        walk = matrix_from(durations_walk, points, "WALK")
        transit = matrix_from(durations_transit, points, "TRANSIT")
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), \
                mock.patch("trips.route_planner._fetch_tables", return_value=(walk, transit, {})):
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        return days[self.day], plan

    def test_uses_travel_time_not_straight_line(self):
        a, b, c = card("A", self.a), card("B", self.b), card("C", self.c)
        a["_key"], b["_key"], c["_key"] = "new:0", "new:1", "new:2"
        points = route_planner._unique_points([a, b, c], HOTEL)
        idx = {p: i for i, p in enumerate(points)}
        h, ia, ib, ic = idx[HOTEL], idx[self.a], idx[self.b], idx[self.c]
        # 직선으로는 A-B가 가장 가깝지만, 둘 사이 이동은 오래 걸리게(도보 불가·대중교통 40분) 만든다.
        walk = {(h, ia): 300, (ia, h): 300, (h, ic): 3000, (ic, h): 3000, (ia, ic): 900, (ic, ia): 900}
        transit = {(h, ia): 300, (ia, h): 300, (h, ib): 600, (ib, h): 600, (ia, ib): 2400, (ib, ia): 2400,
                   (ib, ic): 700, (ic, ib): 700, (h, ic): 1500, (ic, h): 1500, (ia, ic): 900, (ic, ia): 900}
        ordered, plan = self.run_plan([a, b, c], walk, transit)
        self.assertEqual(plan.basis, "google")
        titles = [c_["title"] for c_ in ordered]
        # A와 B를 이어 가는 구간(40분)을 피하고 A -> C -> B 순서가 된다.
        self.assertEqual(titles, ["A", "C", "B"])
        self.assertEqual(plan.order[self.day.isoformat()], ["new:0", "new:2", "new:1"])
        legs = plan.days[self.day].legs
        self.assertEqual([leg["mode"] for leg in legs], ["walk", "transit"])
        self.assertEqual([leg["minutes"] for leg in legs], [15, 12])  # Google이 준 값 그대로(부담 가중치는 표시 안 함)

    def test_avoids_back_and_forth_and_keeps_pinned_cards(self):
        existing = card("기존 장소", self.c)
        existing["id"] = 99
        a, b = card("A", self.a), card("B", self.b)
        a["_key"], b["_key"] = "new:0", "new:1"
        points = route_planner._unique_points([existing, a, b], HOTEL)
        idx = {p: i for i, p in enumerate(points)}
        h, ia, ib, ic = idx[HOTEL], idx[self.a], idx[self.b], idx[self.c]
        t = {(h, ia): 300, (ia, h): 300, (h, ib): 400, (ib, h): 400, (ia, ib): 200, (ib, ia): 200,
             (h, ic): 1800, (ic, h): 1800, (ia, ic): 1700, (ic, ia): 1700, (ib, ic): 1600, (ic, ib): 1600}
        ordered, _ = self.run_plan([existing, a, b], {}, t)
        titles = [c_["title"] for c_ in ordered]
        self.assertEqual(titles[-1], "기존 장소")  # 사용자가 둔 일정은 순서를 바꾸지 않는다
        self.assertEqual(titles[:2], ["A", "B"])  # 새 장소 둘은 붙여서(왕복 없이)

    def test_opening_hours_conflict_is_avoided(self):
        # 월요일 오후 1시에 닫는 곳(A)은 아침에 가야 한다. 이동 시간만 보면 B -> A가 더 가깝다.
        a = card("A", self.a, opening_hours=["월요일: 오전 9:00~오후 12:00"], stay_minutes=60)
        b = card("B", self.b, stay_minutes=240)
        a["_key"], b["_key"] = "new:0", "new:1"
        points = route_planner._unique_points([a, b], HOTEL)
        idx = {p: i for i, p in enumerate(points)}
        h, ia, ib = idx[HOTEL], idx[self.a], idx[self.b]
        t = {(h, ia): 1200, (ia, h): 1200, (h, ib): 300, (ib, h): 300, (ia, ib): 300, (ib, ia): 300}
        ordered, plan = self.run_plan([b, a], {}, t)  # 입력 순서는 B, A (거리상 B 먼저가 유리)
        self.assertEqual([c_["title"] for c_ in ordered], ["A", "B"])
        self.assertEqual(plan.days[self.day].warnings, [])

    def test_unavoidable_conflict_is_reported(self):
        a = card("A", self.a, opening_hours=["월요일: 휴무일"])
        a["_key"] = "new:0"
        points = route_planner._unique_points([a], HOTEL)
        idx = {p: i for i, p in enumerate(points)}
        t = {(idx[HOTEL], idx[self.a]): 300, (idx[self.a], idx[HOTEL]): 300}
        _, plan = self.run_plan([a], {}, t)
        self.assertIn("영업시간 밖", plan.days[self.day].warnings[0])

    def test_no_data_legs_are_not_invented(self):
        a, b, c = card("A", self.a), card("B", self.b), card("C", self.c)
        a["_key"], b["_key"], c["_key"] = "new:0", "new:1", "new:2"
        points = route_planner._unique_points([a, b, c], HOTEL)
        idx = {p: i for i, p in enumerate(points)}
        h, ia, ib, ic = idx[HOTEL], idx[self.a], idx[self.b], idx[self.c]
        # B와 이어지는 구간(A-B, B-C)은 도보·대중교통 모두 경로 없음, 호텔과의 구간과 A-C만 있다.
        t = {(h, ia): 300, (ia, h): 300, (h, ib): 400, (ib, h): 400, (h, ic): 500, (ic, h): 500,
             (ia, ic): 600, (ic, ia): 600}
        ordered, plan = self.run_plan([a, b, c], {}, t)
        self.assertEqual(plan.basis, "partial")
        self.assertIn("찾지 못했어요", plan.note)
        legs = plan.days[self.day].legs
        self.assertIn(None, legs)  # 없는 구간의 시간을 만들어 보여주지 않는다
        self.assertTrue(any(legs))

    def test_drive_time_orders_but_is_never_shown(self):
        # 대중교통이 없고 도보가 오래 걸리는 구간: 자동차 시간으로 순서는 고르되 택시·차량으로 표시하지 않는다.
        a, b, c = card("A", self.a), card("B", self.b), card("C", self.c)
        a["_key"], b["_key"], c["_key"] = "new:0", "new:1", "new:2"
        days = {self.day: [a, b, c]}
        points = route_planner._unique_points([a, b, c], HOTEL)
        n = len(points)
        walk = {(i, j): (routes.Leg("WALK", 0, 0) if i == j else routes.Leg("WALK", 3 * 3600, 9000))
                for i in range(n) for j in range(n)}
        drive = {(i, j): routes.Leg("DRIVE", 0 if i == j else 600, 4000) for i in range(n) for j in range(n)}
        transit = {(i, j): (routes.Leg("TRANSIT", 0, 0) if i == j else None) for i in range(n) for j in range(n)}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}),                 mock.patch("trips.route_planner._fetch_tables", return_value=(walk, transit, drive)):
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        self.assertEqual(plan.days[self.day].legs, [None, None])  # 택시·차량 이동은 표시하지 않는다
        self.assertEqual(plan.basis, "partial")  # 순서는 자동차 시간 기준으로 정했고, 표시할 이동 정보만 없다
        self.assertIn("찾지 못했어요", plan.note)

    def test_routes_unavailable_keeps_straight_line_order_and_says_so(self):
        a, b = card("A", self.a), card("B", self.b)
        a["_key"], b["_key"] = "new:0", "new:1"
        days = {self.day: [a, b]}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": ""}):
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        self.assertEqual((plan.basis, [c["title"] for c in days[self.day]]), ("straight_line", ["A", "B"]))
        self.assertIn("직선거리", plan.note)
        self.assertEqual(plan.order, {})

    def test_unsupported_area_falls_back(self):
        far = card("먼 곳", (13.75, 100.50))  # 방콕
        far["_key"] = "new:0"
        days = {self.day: [far]}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), mock.patch("trips.routes._post") as post:
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        post.assert_not_called()
        self.assertEqual(plan.basis, "straight_line")
        self.assertIn("지원하지 않아", plan.note)

    def test_budget_exceeded_falls_back(self):
        a = card("A", self.a)
        a["_key"] = "new:0"
        days = {self.day: [a]}
        with override_settings(ROUTES_MAX_ELEMENTS_PER_PROPOSAL=1), \
                mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), mock.patch("trips.routes._post") as post:
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        post.assert_not_called()
        self.assertEqual(plan.basis, "straight_line")
        self.assertIn("한도", plan.note)

    def test_apply_order_requires_same_cards(self):
        x, y = card("X", self.a), card("Y", self.b)
        x["_key"], y["_key"] = "new:0", "new:1"
        days = {self.day: [x, y]}
        route_planner.apply_order(days, {self.day.isoformat(): ["new:1", "new:0"]})
        self.assertEqual([c["title"] for c in days[self.day]], ["Y", "X"])
        route_planner.apply_order(days, {self.day.isoformat(): ["new:1"]})  # 구성이 다르면 건드리지 않는다
        self.assertEqual([c["title"] for c in days[self.day]], ["Y", "X"])


class ProposeApplyFlowTests(APITestCase):
    """제안 미리보기의 순서·이동 정보와, 적용했을 때 저장되는 순서가 같다."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="flow@example.com", email="flow@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2030-01-07", end_date="2030-01-07", itinerary_initialized=True)
        Hotel.objects.create(trip=self.trip, name="호텔", address="", latitude=HOTEL[0], longitude=HOTEL[1],
                             check_in="2030-01-06", check_out="2030-01-08")
        self.places = {
            "스카이트리": (35.7101, 139.8107), "도쿄타워": (35.6586, 139.7454), "아사쿠사": (35.7148, 139.7967),
        }

    def plan(self):
        additions = [
            ai_planner.PlanAddition(name=name, search_query=name, kind="sight", day_index=0, time=None,
                                    stay_minutes=90)
            for name in self.places
        ]
        return ai_planner.PlanResponse(reply="좋아요", additions=additions, remove_item_ids=[], moves=[], form=None,
                                       confirm=None, flight=None, hotel_change=None, off_topic=False)

    def search(self, text, *args):
        point = self.places[text]
        return {"place_id": text, "name": text, "address": "", "latitude": point[0], "longitude": point[1],
                "phone": "", "opening_hours": []}

    def fake_tables(self, day, points, budget, country=None):
        # 이동 시간: 좌표 사이 거리(km) x 4분 (도보 불가), 대중교통만 사용
        from .itinerary_planner import distance_km
        n = len(points)
        transit = {(i, j): routes.Leg("TRANSIT", int(distance_km(points[i], points[j]) * 240), 1000)
                   for i in range(n) for j in range(n)}
        walk = {(i, j): (routes.Leg("WALK", 0, 0) if i == j else None) for i in range(n) for j in range(n)}
        return walk, transit, {}

    def post_propose(self):
        with mock.patch("trips.ai_planner.propose", return_value=self.plan()), \
                mock.patch("trips.places.search_place", side_effect=self.search), \
                mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), \
                mock.patch("trips.route_planner._fetch_tables", side_effect=self.fake_tables):
            return self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                    {"messages": [{"role": "user", "content": "하루 일정 짜줘"}]}, format="json")

    def test_preview_has_route_info_and_apply_saves_same_order_without_calling_routes(self):
        response = self.post_propose()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["route"]["basis"], "google")
        day = response.data["preview"][0]
        titles = [item["title"] for item in day["items"]]
        self.assertEqual(len(day["legs"]), len(titles) - 1)
        self.assertTrue(all(leg and leg["mode"] == "transit" and leg["minutes"] > 0 for leg in day["legs"]))
        self.assertTrue(all(item["eta"] for item in day["items"]))
        # 직선거리(호텔에서 가까운 순)가 아니라 이동 시간이 짧은 순서: 도쿄타워 -> 아사쿠사 -> 스카이트리
        self.assertEqual(titles, ["도쿄타워", "아사쿠사", "스카이트리"])
        self.assertTrue(response.data["proposal"]["order"])

        with mock.patch("trips.route_planner._fetch_tables") as fetch:  # 적용할 때는 Routes API를 부르지 않는다
            applied = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/apply/",
                                       {"proposal": response.data["proposal"]}, format="json")
        fetch.assert_not_called()
        self.assertEqual(applied.status_code, status.HTTP_200_OK)
        saved = list(self.trip.itinerary_items.order_by("order").values_list("title", flat=True))
        self.assertEqual(saved, titles)  # 미리본 순서 = 저장된 순서(지도 핀 순서)

    def test_without_routes_preview_says_straight_line(self):
        with mock.patch("trips.ai_planner.propose", return_value=self.plan()), \
                mock.patch("trips.places.search_place", side_effect=self.search), \
                mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": ""}):
            response = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                        {"messages": [{"role": "user", "content": "하루 일정 짜줘"}]}, format="json")
        self.assertEqual(response.data["route"]["basis"], "straight_line")
        self.assertIn("직선거리", response.data["route"]["note"])
        self.assertTrue(all(leg is None for leg in response.data["preview"][0]["legs"]))
        self.assertEqual(response.data["proposal"]["order"], {})
        self.assertTrue(all(not item["eta"] for item in response.data["preview"][0]["items"]))

    def test_ai_schema_has_no_travel_time_fields(self):
        names = set(ai_planner.PlanAddition.model_fields) | set(ai_planner.PlanResponse.model_fields)
        for forbidden in ("travel_time", "duration", "transit", "route", "mode", "minutes_to_next"):
            self.assertNotIn(forbidden, names)
        self.assertIn("stay_minutes", ai_planner.PlanAddition.model_fields)


NAVITIME_SAMPLE = {"items": [{"summary": {"move": {"transit_count": 1, "walk_distance": 360, "time": 26, "distance": 10660,
                                                 "move_type": ["rapid_train", "walk"]}}}]}


class NavitimeTests(TestCase):
    """일본 대중교통은 NAVITIME에서 가져온다: 응답 해석·캐시·한도·실패 처리."""

    def setUp(self):
        cache.clear()
        self.a, self.b = (35.6896, 139.7006), (35.6812, 139.7671)
        self.day = date(2030, 1, 7)

    def fetch(self, count=1, **env):
        env = {"NAVITIME_RAPIDAPI_KEY": "k", **env}
        with mock.patch.dict("os.environ", env):
            return transit.fetch_legs([(self.a, self.b, self.day, 600)] * count, transit.TransitBudget())

    def test_parses_time_distance_and_transfers(self):
        with mock.patch("trips.transit._request", return_value=(NAVITIME_SAMPLE, 450)):
            legs = self.fetch()
        self.assertEqual(legs, [transit.TransitLeg(26, 10660, 1)])

    def test_cache_and_budget(self):
        with mock.patch("trips.transit._request", return_value=(NAVITIME_SAMPLE, 450)) as request:
            self.fetch()
            self.fetch()  # 같은 구간·같은 시간대는 다시 부르지 않는다
        self.assertEqual(request.call_count, 1)
        with override_settings(NAVITIME_MAX_REQUESTS_PER_PROPOSAL=0), mock.patch("trips.transit._request") as request:
            cache.clear()
            self.assertEqual(self.fetch(), [None])
        request.assert_not_called()

    def test_stops_when_monthly_quota_is_nearly_used(self):
        cache.set("navitime:remaining", 5, 60)  # 응답 헤더의 남은 횟수가 예비분 이하
        with mock.patch("trips.transit._request") as request:
            self.assertEqual(self.fetch(), [None])
        request.assert_not_called()

    def test_failure_or_no_route_is_not_invented(self):
        with mock.patch("trips.transit._request", return_value=(None, None)):
            self.assertEqual(self.fetch(), [None])
        with mock.patch("trips.transit._request", return_value=({"items": []}, 100)):
            self.assertEqual(self.fetch(), [None])

    def test_disabled_without_key(self):
        with mock.patch("trips.transit._request") as request:
            self.assertEqual(self.fetch(NAVITIME_RAPIDAPI_KEY=""), [None])
        request.assert_not_called()

    def test_start_time_uses_representative_date_and_half_hour(self):
        value = transit.start_time_for(date(2020, 1, 6), 14 * 60 + 40)  # 지난 월요일 -> 가까운 미래의 월요일
        self.assertTrue(value.endswith("T14:30:00"))
        self.assertEqual(datetime.fromisoformat(value).weekday(), 0)


class NavitimeInPlanTests(OrderingTests):
    """도보로 갈 수 없는 구간은 순서를 정한 뒤 NAVITIME 대중교통 시간으로 표시한다."""

    def test_far_legs_show_navitime_transit_and_update_eta(self):
        a, b = card("A", self.a), card("B", self.c)  # 먼 두 곳(도보 3시간, 대중교통은 Google에 없음)
        a["_key"], b["_key"] = "new:0", "new:1"
        days = {self.day: [a, b]}
        points = route_planner._unique_points([a, b], HOTEL)
        n = len(points)
        walk = {(i, j): (routes.Leg("WALK", 0, 0) if i == j else routes.Leg("WALK", 3 * 3600, 9000)) for i in range(n) for j in range(n)}
        drive = {(i, j): routes.Leg("DRIVE", 0 if i == j else 900, 9000) for i in range(n) for j in range(n)}
        none_transit = {(i, j): (routes.Leg("TRANSIT", 0, 0) if i == j else None) for i in range(n) for j in range(n)}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k", "NAVITIME_RAPIDAPI_KEY": "k"}),                 mock.patch("trips.route_planner._fetch_tables", return_value=(walk, none_transit, drive)),                 mock.patch("trips.transit._request", return_value=(NAVITIME_SAMPLE, 400)) as request:
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        self.assertEqual(request.call_count, 1)  # 이어지는 구간(A -> B) 한 건만 호출한다
        self.assertEqual(plan.basis, "google")
        self.assertEqual(plan.days[self.day].legs, [{"mode": "transit", "minutes": 26, "meters": 10660, "transfers": 1}])

    def test_navitime_unavailable_leaves_no_info_not_taxi(self):
        a, b = card("A", self.a), card("B", self.c)
        a["_key"], b["_key"] = "new:0", "new:1"
        days = {self.day: [a, b]}
        points = route_planner._unique_points([a, b], HOTEL)
        n = len(points)
        walk = {(i, j): (routes.Leg("WALK", 0, 0) if i == j else routes.Leg("WALK", 3 * 3600, 9000)) for i in range(n) for j in range(n)}
        drive = {(i, j): routes.Leg("DRIVE", 0 if i == j else 900, 9000) for i in range(n) for j in range(n)}
        none_transit = {(i, j): (routes.Leg("TRANSIT", 0, 0) if i == j else None) for i in range(n) for j in range(n)}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k", "NAVITIME_RAPIDAPI_KEY": ""}),                 mock.patch("trips.route_planner._fetch_tables", return_value=(walk, none_transit, drive)):
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        self.assertEqual(plan.days[self.day].legs, [None])
        self.assertEqual(plan.basis, "partial")


SEOUL = (37.5665, 126.9780)
SEOUL_GANGNAM = (37.4979, 127.0276)


class ServiceAreaTests(TestCase):
    """지원 지역은 나라(기본 동아시아) 단위다. 일본은 NAVITIME, 그 밖의 나라는 Google 대중교통을 쓴다."""

    def setUp(self):
        cache.clear()
        owner = User.objects.create_user(username="area@example.com")
        self.trip = Trip.objects.create(owner=owner, destinations=[{"city": "서울", "city_code": "seoul"}],
                                        start_date="2030-01-07", end_date="2030-01-07", itinerary_initialized=True)
        self.day = date(2030, 1, 7)

    def test_east_asia_is_supported_by_default(self):
        self.assertEqual(routes.service_area(TOKYO_STATION), "JP")
        self.assertEqual(routes.service_area(SEOUL), "KR")
        self.assertEqual(routes.service_area((25.0478, 121.5170)), "TW")  # 타이베이
        self.assertEqual(routes.service_area((22.2820, 114.1580)), "HK")
        self.assertIsNone(routes.service_area((13.7563, 100.5018)))  # 방콕은 아직 아님
        self.assertIsNone(routes.service_area((39.9087, 116.3975)))  # 중국 본토는 Google이 대중교통 경로를 주지 않아 기본에서 제외

    @override_settings(ROUTES_COUNTRIES=["JP"], ROUTES_CITIES=["bangkok"])
    def test_countries_and_extra_cities_are_configurable(self):
        self.assertIsNone(routes.service_area(SEOUL))
        self.assertEqual(routes.service_area((13.7563, 100.5018)), "TH")

    def test_timezone_follows_country(self):
        now = datetime(2026, 10, 15, 3, 0, tzinfo=dt_timezone.utc)
        value_kr, _ = routes.departure_for(date(2026, 10, 17), now=now, country="KR")
        value_tw, _ = routes.departure_for(date(2026, 10, 17), now=now, country="TW")
        self.assertEqual(value_kr, "2026-10-17T02:00:00Z")  # 서울 11시 = 02:00Z
        self.assertEqual(value_tw, "2026-10-17T03:00:00Z")  # 타이베이 11시 = 03:00Z

    def plan(self, points_cards, tables, navitime_key="k"):
        days = {self.day: points_cards}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k", "NAVITIME_RAPIDAPI_KEY": navitime_key}),                 mock.patch("trips.route_planner._fetch_tables", return_value=tables) as fetch,                 mock.patch("trips.transit._request", return_value=(NAVITIME_SAMPLE, 400)) as navitime:
            plan = route_planner.plan_days(self.trip, days, user_id=1)
        return plan, fetch, navitime

    def seoul_cards(self):
        a, b = card("광화문", SEOUL), card("강남", SEOUL_GANGNAM)
        a["_key"], b["_key"] = "new:0", "new:1"
        return [a, b]

    def test_korea_uses_google_transit_and_never_calls_navitime(self):
        cards = self.seoul_cards()
        points = route_planner._unique_points(cards, route_planner.day_anchor(self.trip, self.day, cards))
        n = len(points)
        walk = {(i, j): (routes.Leg("WALK", 0, 0) if i == j else routes.Leg("WALK", 7200, 9000)) for i in range(n) for j in range(n)}
        transit_ = {(i, j): (routes.Leg("TRANSIT", 0, 0) if i == j else routes.Leg("TRANSIT", 1500, 9500)) for i in range(n) for j in range(n)}
        plan, fetch, navitime = self.plan(cards, (walk, transit_, {}))
        self.assertEqual(fetch.call_args.args[3], None)  # 일본이 아니면 Google 대중교통 행렬도 받는다
        navitime.assert_not_called()
        self.assertEqual(plan.days[self.day].legs[0]["mode"], "transit")
        self.assertEqual(plan.days[self.day].legs[0]["minutes"], 25)

    def test_japan_skips_google_transit_matrix(self):
        a, b = card("A", TOKYO_STATION), card("B", HOTEL)
        a["_key"], b["_key"] = "new:0", "new:1"
        trip = self.trip
        points = route_planner._unique_points([a, b], HOTEL)
        n = len(points)
        walk = {(i, j): (routes.Leg("WALK", 0, 0) if i == j else routes.Leg("WALK", 7200, 9000)) for i in range(n) for j in range(n)}
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}),                 mock.patch("trips.routes._post", return_value=[]) as post,                 mock.patch("trips.routes.travel_matrix", wraps=routes.travel_matrix) as matrix:
            try:
                route_planner._fetch_tables(self.day, points, routes.Budget(1), "JP")
            except routes.RoutesError:
                pass
        modes = [call.args[1] for call in matrix.call_args_list]
        self.assertNotIn("TRANSIT", modes)  # 일본은 Google 대중교통을 부르지 않아 요소 수(비용)를 아낀다
        self.assertEqual(trip.pk, self.trip.pk)


class StayAndArrivalStorageTests(ProposeApplyFlowTests):
    """AI가 정한 체류 시간과 계산한 예상 도착 시각이 DB에 저장된다. 순서·시간이 바뀌면 추정치는 지운다."""

    def plan_with_stay(self):
        plan = self.plan()
        for addition, minutes in zip(plan.additions, (120, 60, None)):
            addition.stay_minutes = minutes
        return plan

    def propose_and_apply(self):
        with mock.patch("trips.ai_planner.propose", return_value=self.plan_with_stay()), \
                mock.patch("trips.places.search_place", side_effect=self.search), \
                mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k"}), \
                mock.patch("trips.route_planner._fetch_tables", side_effect=self.fake_tables):
            proposed = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                        {"messages": [{"role": "user", "content": "하루 일정 짜줘"}]}, format="json")
        applied = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/apply/",
                                   {"proposal": proposed.data["proposal"]}, format="json")
        self.assertEqual(applied.status_code, status.HTTP_200_OK)
        return proposed, applied

    def test_apply_saves_stay_minutes_and_expected_arrival_from_preview(self):
        proposed, applied = self.propose_and_apply()
        items = {item.title: item for item in self.trip.itinerary_items.all()}
        # 체류 시간: AI가 정한 값만 저장한다(정하지 않은 곳은 비워 둔다).
        self.assertEqual({t: i.stay_minutes for t, i in items.items()},
                         {"스카이트리": 120, "도쿄타워": 60, "아사쿠사": None})
        # 예상 도착 시각: 미리보기에서 보여 준 값과 같다.
        preview = {item["title"]: item["eta"] for item in proposed.data["preview"][0]["items"]}
        saved = {t: i.expected_arrival.strftime("%H:%M") for t, i in items.items()}
        self.assertEqual(saved, preview)
        # 일정 조회 API에도 내려간다.
        listed = {item["title"]: item for item in applied.data["items"]}
        self.assertEqual(listed["스카이트리"]["stay_minutes"], 120)
        self.assertEqual(listed["도쿄타워"]["expected_arrival"], preview["도쿄타워"])

    def test_without_routes_nothing_is_estimated(self):
        with mock.patch("trips.ai_planner.propose", return_value=self.plan_with_stay()), \
                mock.patch("trips.places.search_place", side_effect=self.search), \
                mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": ""}):
            proposed = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                        {"messages": [{"role": "user", "content": "하루 일정 짜줘"}]}, format="json")
        self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/apply/", {"proposal": proposed.data["proposal"]}, format="json")
        self.assertEqual(proposed.data["proposal"]["etas"], {})
        self.assertFalse(self.trip.itinerary_items.exclude(expected_arrival=None).exists())  # 도착 시각은 만들지 않는다
        self.assertEqual(set(self.trip.itinerary_items.values_list("stay_minutes", flat=True)), {120, 60, None})

    def arrivals(self):
        return list(self.trip.itinerary_items.values_list("expected_arrival", flat=True))

    def test_manual_changes_clear_stale_arrivals(self):
        self.propose_and_apply()
        self.assertTrue(all(self.arrivals()))
        items = list(self.trip.itinerary_items.order_by("order"))
        # 순서 바꾸기
        self.client.post(f"/api/v1/trips/{self.trip.pk}/itinerary/reorder/",
                         {"day": "2030-01-07", "ids": [i.id for i in reversed(items)]}, format="json")
        self.assertEqual(self.arrivals(), [None, None, None])

        self.propose_and_apply_again = None
        # 시간 수정
        ItineraryItem.objects.filter(pk=items[0].pk).update(expected_arrival="10:00")
        self.client.patch(f"/api/v1/itinerary-items/{items[0].pk}/", {"time": "13:00"}, format="json")
        self.assertIsNone(ItineraryItem.objects.get(pk=items[0].pk).expected_arrival)
        # 삭제
        ItineraryItem.objects.filter(pk=items[1].pk).update(expected_arrival="11:00")
        self.client.delete(f"/api/v1/itinerary-items/{items[2].pk}/")
        self.assertIsNone(ItineraryItem.objects.get(pk=items[1].pk).expected_arrival)

    def test_direct_add_clears_that_days_arrivals(self):
        self.propose_and_apply()
        detail = {"place_id": "p", "name": "시부야", "address": "", "latitude": 35.659, "longitude": 139.70,
                  "phone": "", "opening_hours": []}
        with mock.patch("trips.places.place_details", return_value=detail):
            self.client.post(f"/api/v1/trips/{self.trip.pk}/itinerary/",
                             {"kind": "sight", "day": "2030-01-07", "place_id": "p"}, format="json")
        self.assertFalse(self.trip.itinerary_items.exclude(expected_arrival=None).exists())

    def test_fallback_day_clears_instead_of_keeping_old_arrivals(self):
        self.propose_and_apply()
        self.assertTrue(all(self.arrivals()))
        # 같은 날에 새 장소를 AI로 더 넣는데 이번에는 Routes를 쓸 수 없는 경우: 옛 추정치는 지운다.
        extra = ai_planner.PlanResponse(
            reply="추가", remove_item_ids=[], moves=[], form=None, confirm=None, flight=None, hotel_change=None,
            off_topic=False,
            additions=[ai_planner.PlanAddition(name="스카이트리", search_query="스카이트리", kind="sight", day_index=0,
                                               time=None, stay_minutes=30)],
        )
        with mock.patch("trips.ai_planner.propose", return_value=extra), \
                mock.patch("trips.places.search_place", side_effect=self.search), \
                mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": ""}):
            proposed = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                        {"messages": [{"role": "user", "content": "하나 더"}]}, format="json")
        self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/apply/", {"proposal": proposed.data["proposal"]}, format="json")
        self.assertFalse(self.trip.itinerary_items.exclude(expected_arrival=None).exists())


class NoFixedPlaceLimitTests(TestCase):
    """하루 장소 수의 고정 상한은 없다. 날짜를 정하지 않은 장소만 시간이 남은 날로 보낸다(거절하지 않는다)."""

    def setUp(self):
        owner = User.objects.create_user(username="cap@example.com")
        self.trip = Trip.objects.create(owner=owner, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2030-01-07", end_date="2030-01-08", itinerary_initialized=True)
        self.days = {date(2030, 1, 7): [], date(2030, 1, 8): []}

    def add(self, count, day=None, stay=60):
        from .itinerary_planner import place_cards
        cards = [card(f"장소{i}", (35.69 + i * 0.001, 139.70), stay_minutes=stay, day=day) for i in range(count)]
        return place_cards(self.trip, self.days, cards)

    def test_more_than_five_places_fit_in_a_day_when_time_allows(self):
        placed = self.add(7, stay=60)  # 60 + 이동 30 = 90분씩, 7곳 = 630분 < 13시간
        self.assertEqual(placed, [date(2030, 1, 7)] * 7)  # 예전 상한(5곳)이었다면 6번째부터 다른 날로 갔다

    def test_overflow_goes_to_the_next_day_without_rejecting(self):
        placed = self.add(10, stay=90)  # 120분씩: 6곳(720분)까지가 첫날, 나머지는 둘째 날
        self.assertEqual(placed.count(date(2030, 1, 7)), 6)
        self.assertEqual(placed.count(date(2030, 1, 8)), 4)

    def test_flight_day_has_a_smaller_budget(self):
        self.days[date(2030, 1, 7)].append({"kind": "flight", "title": "항공", "time": "", "time_label": "출국", "stops": []})
        placed = self.add(4, stay=90)  # 항공편이 있는 날은 6시간: 120분씩 3곳
        self.assertEqual(placed.count(date(2030, 1, 7)), 3)

    def test_explicit_day_is_never_limited(self):
        placed = self.add(12, day=date(2030, 1, 7), stay=90)  # 직접 추가처럼 날짜를 정하면 상한이 없다
        self.assertEqual(placed, [date(2030, 1, 7)] * 12)

    def test_everything_full_still_places(self):
        placed = self.add(30, stay=120)
        self.assertEqual(len(placed), 30)
