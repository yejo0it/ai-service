"""
일정 카드 사이 이동 구간 상세(trips.legs) 테스트. Google Routes·NAVITIME은 모두 모킹하고,
응답 해석은 실제 응답(시부야→도쿄타워, 서울 경복궁→홍대입구)을 줄인 고정 데이터로 확인한다.
"""

from datetime import date, time
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from .. import legs, routes
from ..models import ItineraryItem, Trip

User = get_user_model()

SHIBUYA = (35.6580, 139.7016)
TOKYO_TOWER = (35.6586, 139.7454)
NARITA = (35.7720, 140.3929)
FAR_AWAY = (13.7563, 100.5018)  # 방콕: 지원 지역 밖

NAVITIME_ROUTE = {
    "items": [
        {
            "summary": {
                "move": {
                    "time": 37, "distance": 10700, "transit_count": 1,
                    "reference_fare": {"lowest_total_ticket": 260.0, "lowest_total_ic": 253.0},
                }
            },
            "sections": [
                {"type": "point", "name": "start", "coord": {"lat": 35.658, "lon": 139.7016}},
                {"type": "move", "move": "walk", "from_time": "2026-10-22T10:00:00+09:00", "time": 2, "distance": 130},
                {"type": "point", "name": "渋谷", "node_id": "00003544", "node_types": ["station"], "gateway": "東口",
                 "coord": {"lat": 35.65864, "lon": 139.70206},
                 "numbering": {"departure": [{"symbol": "JY", "number": "20"}]}},
                {"type": "move", "move": "local_train", "next_transit": True, "transfer_seconds": 180,
                 "from_time": "2026-10-22T10:04:00+09:00", "time": 5, "line_name": "ＪＲ山手線",
                 "transport": {"name": "ＪＲ山手線", "color": "#80C241", "company": {"id": "4", "name": "ＪＲ東日本"},
                               "links": [{"name": "ＪＲ山手線", "direction": "up",
                                          "destination": {"id": "00007825", "name": "品川"},
                                          "from": {"id": "00003544", "name": "渋谷"}, "to": {"id": "00008684", "name": "目黒"}}]}},
                {"type": "point", "name": "目黒", "node_id": "00008684", "node_types": ["station"],
                 "coord": {"lat": 35.634082, "lon": 139.715901},
                 "numbering": {"arrival": [{"symbol": "JY", "number": "22"}], "departure": [{"symbol": "I", "number": "01"}]}},
                {"type": "move", "move": "local_train", "from_time": "2026-10-22T10:14:00+09:00", "time": 12,
                 "line_name": "都営三田線",
                 "transport": {"name": "都営三田線", "color": "#0079C2", "company": {"id": "121", "name": "東京都交通局"},
                               "links": [{"name": "都営三田線", "destination": {"id": "1", "name": "西高島平"},
                                          "from": {"id": "00008684", "name": "目黒"}, "to": {"id": "00002292", "name": "御成門"}}]}},
                {"type": "point", "name": "御成門", "node_id": "00002292", "node_types": ["station"], "gateway": "A1口",
                 "coord": {"lat": 35.659422, "lon": 139.750455}, "numbering": {"arrival": [{"symbol": "I", "number": "06"}]}},
                {"type": "move", "move": "walk", "from_time": "2026-10-22T10:26:00+09:00", "time": 11, "distance": 759},
                {"type": "point", "name": "goal", "coord": {"lat": 35.6586, "lon": 139.7454}},
            ],
        }
    ]
}

GOOGLE_ROUTE = {
    "routes": [
        {
            "duration": "2246s", "distanceMeters": 7147,
            "legs": [{"steps": [
                {"distanceMeters": 227, "staticDuration": "228s", "travelMode": "WALK"},
                {"distanceMeters": 1671, "staticDuration": "311s", "travelMode": "TRANSIT",
                 "transitDetails": {
                     "stopDetails": {"arrivalStop": {"name": "시청역"}, "arrivalTime": "2026-10-22T02:19:55Z",
                                     "departureStop": {"name": "국립민속박물관"}, "departureTime": "2026-10-22T02:14:44Z"},
                     "transitLine": {"name": "서울 마을버스", "color": "#0abb0c", "nameShort": "종로11"}, "stopCount": 4}},
                {"distanceMeters": 215, "staticDuration": "215s", "travelMode": "WALK"},
                {"staticDuration": "60s", "travelMode": "WALK"},
                {"staticDuration": "0s", "travelMode": "WALK"},
                {"distanceMeters": 4879, "staticDuration": "600s", "travelMode": "TRANSIT",
                 "transitDetails": {
                     "stopDetails": {"arrivalStop": {"name": "홍대입구"}, "arrivalTime": "2026-10-22T02:37:00Z",
                                     "departureStop": {"name": "시청"}, "departureTime": "2026-10-22T02:27:00Z"},
                     "transitLine": {"name": "서울 지하철 2호선", "color": "#35b12b", "nameShort": "2호선"}, "stopCount": 5}},
                {"distanceMeters": 82, "staticDuration": "83s", "travelMode": "WALK"},
            ]}],
        }
    ]
}


# 한국어 역 이름 데이터(실제로는 data/station_names_ja_ko.json). 테스트에서는 몇 개만 주입한다.
STATION_INDEX = {
    "渋谷": [(35.6585, 139.7013, "시부야역")],
    "目黒": [(35.6340, 139.7160, "메구로역")],
    "御成門": [(35.6614, 139.7515, "오나리몬역")],
    "品川": [(35.6286, 139.7392, "시나가와역")],
}


def with_station_data(index=STATION_INDEX):
    return mock.patch("trips.station_names._load_index", return_value=index)


class ParseNavitimeTests(SimpleTestCase):
    def test_korean_names_with_originals_templates_and_numbers(self):
        with with_station_data():
            route = legs.parse_navitime(NAVITIME_ROUTE, with_times=True)
        self.assertEqual((route["total_minutes"], route["fare_label"]), (37, "¥253"))  # IC 요금
        walk1, jr, toei, walk2 = route["steps"]
        # 도보: 한국어 템플릿 + 역 이름은 한국어(원어), 출구는 한국어로
        self.assertEqual(walk1["description"], "도보 2분 · 130m · 시부야역(渋谷駅) 동쪽 출구까지")
        self.assertEqual(walk1["start_time"], "10:00")
        # 탑승: 노선·운영사·행선지·역·역 번호·환승 시간
        self.assertEqual(
            {key: jr[key] for key in ("line_name", "line_name_ja", "operator", "operator_ja", "from_stop", "from_stop_ja",
                                      "to_stop", "to_stop_ja", "from_number", "to_number", "direction", "direction_ja",
                                      "transfer_minutes", "minutes", "start_time", "line_color")},
            {"line_name": "JR야마노테선", "line_name_ja": "JR山手線", "operator": "JR동일본", "operator_ja": "JR東日本",
             "from_stop": "시부야역", "from_stop_ja": "渋谷駅", "to_stop": "메구로역", "to_stop_ja": "目黒駅",
             "from_number": "JY20", "to_number": "JY22", "direction": "시나가와행", "direction_ja": "品川行",
             "transfer_minutes": 3, "minutes": 5, "start_time": "10:04", "line_color": "#80C241"},
        )
        self.assertEqual((jr["train_type"], jr["train_type_ja"]), ("", ""))  # 보통 열차는 종별을 따로 보여주지 않는다
        self.assertEqual((toei["line_name"], toei["operator"], toei["from_stop"], toei["to_stop"], toei["transfer_minutes"]),
                         ("도에이 미타선", "도쿄도교통국(도에이)", "메구로역", "오나리몬역", None))
        self.assertEqual(toei["direction"], "西高島平行")  # 확보하지 못한 행선지는 원어 그대로
        self.assertEqual(walk2["description"], "오나리몬역(御成門駅) A1 출구에서 도보 11분 · 760m")  # 하차 후 도보

    def test_unregistered_stations_keep_the_original(self):
        with with_station_data({}):  # 데이터가 없거나 모르는 역
            route = legs.parse_navitime(NAVITIME_ROUTE, with_times=True)
        walk1, jr, _, walk2 = route["steps"]
        self.assertEqual(walk1["description"], "도보 2분 · 130m · 渋谷駅 동쪽 출구까지")  # 출구는 규칙으로만 바꾼다
        self.assertEqual((jr["from_stop"], jr["from_stop_ja"], jr["to_stop"], jr["direction"]),
                         ("渋谷駅", "渋谷駅", "目黒駅", "品川行"))
        self.assertEqual(walk2["description"], "御成門駅 A1 출구에서 도보 11분 · 760m")

    def test_start_times_are_hidden_when_departure_is_unknown(self):
        with with_station_data():
            route = legs.parse_navitime(NAVITIME_ROUTE, with_times=False)
        self.assertEqual({step["start_time"] for step in route["steps"]}, {""})

    def test_unreadable_response_is_none(self):
        self.assertIsNone(legs.parse_navitime({"items": []}, True))
        self.assertIsNone(legs.parse_navitime({}, True))
        self.assertIsNone(legs.parse_navitime(None, True))

    def test_default_color_when_missing(self):
        payload = {"items": [{"summary": {"move": {"time": 5}}, "sections": [
            {"type": "move", "move": "local_train", "time": 5, "line_name": "무명선", "transport": {}}]}]}
        step = legs.parse_navitime(payload, True)["steps"][0]
        self.assertEqual((step["line_color"], step["line_name"]), ("#64748b", "무명선"))  # 사전에 없는 이름은 원문 그대로
        self.assertEqual((step["from_stop"], step["direction"], step["operator"], step["transfer_minutes"]), ("", "", "", None))


class ParseGoogleTests(SimpleTestCase):
    def test_merges_walks_and_reads_lines_stops_and_counts(self):
        route = legs.parse_google_transit(GOOGLE_ROUTE, ZoneInfo("Asia/Seoul"), 11 * 60, with_times=True)
        self.assertEqual(route["total_minutes"], 37)
        kinds = [step["type"] for step in route["steps"]]
        self.assertEqual(kinds, ["walk", "transit", "walk", "transit", "walk"])  # 연속된 도보는 하나로 합친다
        bus, subway = route["steps"][1], route["steps"][3]
        self.assertEqual((bus["line_name"], bus["line_color"], bus["from_stop"], bus["to_stop"], bus["stop_count"]),
                         ("종로11", "#0abb0c", "국립민속박물관", "시청역", 4))
        self.assertEqual((subway["line_name"], subway["stop_count"], subway["minutes"], subway["start_time"]),
                         ("2호선", 5, 10, "11:27"))  # 02:27Z = 서울 11:27
        self.assertEqual(route["steps"][0]["description"], "도보 4분 · 230m · 국립민속박물관까지")
        self.assertIsNone(route["fare_label"])  # Google 응답에는 요금을 요청하지 않는다

    def test_empty_or_broken_is_none(self):
        self.assertIsNone(legs.parse_google_transit({}, ZoneInfo("Asia/Seoul"), 600, True))
        self.assertIsNone(legs.parse_google_transit({"routes": [{"duration": "60s", "legs": [{"steps": []}]}]},
                                                    ZoneInfo("Asia/Seoul"), 600, True))


def walk_matrix(seconds):
    return lambda points, mode, **kwargs: {(0, 1): routes.Leg(mode, seconds[mode], 1000) if seconds.get(mode) else None}


class FakeItem:
    def __init__(self, pk, kind, point, time_value=None, expected=None, stay=None):
        self.id, self.kind, self.time, self.expected_arrival, self.stay_minutes = pk, kind, time_value, expected, stay
        self.stops = [{"lat": point[0], "lng": point[1]}]


class DayLegsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.day = date(2030, 1, 7)

    def run_legs(self, items, matrix, navitime=None, google=None, env=None):
        env = {"GOOGLE_ROUTES_API_KEY": "k", "NAVITIME_RAPIDAPI_KEY": "k", **(env or {})}
        with mock.patch.dict("os.environ", env), \
                mock.patch("trips.routes.travel_matrix", side_effect=matrix) as m, \
                mock.patch("trips.transit._request", return_value=(navitime, 400)) as nav, \
                mock.patch("trips.routes._post_directions", return_value=google or {}) as g:
            result = legs.day_legs(items, self.day, user_id=1)
        return result, m, nav, g

    def test_short_distance_is_walk_only(self):
        items = [FakeItem(1, "sight", SHIBUYA), FakeItem(2, "sight", (35.6600, 139.7020))]
        result, _, nav, _ = self.run_legs(items, walk_matrix({"WALK": 480}))
        nav.assert_not_called()
        self.assertEqual(len(result), 1)
        leg = result[0]
        self.assertEqual((leg["from_item_id"], leg["to_item_id"], leg["status"], leg["mode"], leg["total_minutes"]),
                         (1, 2, "ok", "walk", 8))
        self.assertEqual([step["type"] for step in leg["steps"]], ["walk"])

    def test_japan_uses_navitime_with_times_from_stored_schedule(self):
        items = [FakeItem(1, "sight", SHIBUYA, expected=time(9, 0), stay=60), FakeItem(2, "sight", TOKYO_TOWER)]
        result, _, nav, _ = self.run_legs(items, walk_matrix({"WALK": 5400}), navitime=NAVITIME_ROUTE)
        leg = result[0]
        self.assertEqual((leg["mode"], leg["total_minutes"], leg["fare_label"]), ("transit", 37, "¥253"))
        self.assertEqual([s["type"] for s in leg["steps"]], ["walk", "transit", "transit", "walk"])
        self.assertTrue(nav.call_args.args[2].endswith("T10:00:00"))  # 출발 = 예상 도착 9:00 + 체류 60분
        self.assertEqual(leg["steps"][1]["start_time"], "10:04")

    def test_unknown_departure_hides_step_times(self):
        items = [FakeItem(1, "sight", SHIBUYA), FakeItem(2, "sight", TOKYO_TOWER)]
        result, *_ = self.run_legs(items, walk_matrix({"WALK": 5400}), navitime=NAVITIME_ROUTE)
        self.assertEqual({step["start_time"] for step in result[0]["steps"]}, {""})

    def test_second_call_is_cached(self):
        items = [FakeItem(1, "sight", SHIBUYA), FakeItem(2, "sight", TOKYO_TOWER)]
        self.run_legs(items, walk_matrix({"WALK": 5400}), navitime=NAVITIME_ROUTE)
        _, _, nav, _ = self.run_legs(items, walk_matrix({"WALK": 5400}), navitime=NAVITIME_ROUTE)
        nav.assert_not_called()  # 같은 구간·같은 시간대는 외부 API를 다시 부르지 않는다

    def test_no_transit_falls_back_to_taxi_then_walk_then_not_found(self):
        items = [FakeItem(1, "sight", SHIBUYA), FakeItem(2, "sight", TOKYO_TOWER)]
        result, *_ = self.run_legs(items, walk_matrix({"WALK": 5400, "DRIVE": 900}), navitime={"items": []})
        leg = result[0]
        self.assertEqual((leg["mode"], leg["total_minutes"], leg["steps"][0]["type"]), ("drive", 15, "drive"))
        self.assertIn("택시·차량 15분", leg["steps"][0]["description"])

        cache.clear()
        result, *_ = self.run_legs(items, walk_matrix({"WALK": 5400}), navitime={"items": []})
        self.assertEqual((result[0]["mode"], result[0]["total_minutes"]), ("walk", 90))  # 택시 정보도 없으면 도보

        cache.clear()
        result, *_ = self.run_legs(items, walk_matrix({}), navitime={"items": []})
        self.assertEqual((result[0]["status"], result[0]["steps"]), ("not_found", []))  # 만들어 채우지 않는다

    def test_navitime_quota_exhausted_does_not_call_it(self):
        items = [FakeItem(1, "sight", SHIBUYA), FakeItem(2, "sight", TOKYO_TOWER)]
        cache.set("navitime:remaining", 3, 60)
        result, _, nav, _ = self.run_legs(items, walk_matrix({"WALK": 5400, "DRIVE": 600}), navitime=NAVITIME_ROUTE)
        nav.assert_not_called()
        self.assertEqual(result[0]["mode"], "drive")

    def test_korea_uses_google_transit_not_navitime(self):
        seoul_a, seoul_b = (37.5796, 126.9770), (37.5563, 126.9236)
        items = [FakeItem(1, "sight", seoul_a), FakeItem(2, "sight", seoul_b)]
        result, _, nav, g = self.run_legs(items, walk_matrix({"WALK": 9000}), google=GOOGLE_ROUTE)
        nav.assert_not_called()
        self.assertEqual(result[0]["mode"], "transit")
        self.assertEqual(result[0]["steps"][3]["line_name"], "2호선")

    def test_flights_and_unsupported_regions(self):
        flight = FakeItem(2, "flight", NARITA)
        flight.stops = [{"lat": 37.46, "lng": 126.44}, {"lat": NARITA[0], "lng": NARITA[1]}]  # 인천 -> 나리타
        items = [FakeItem(1, "sight", SHIBUYA), flight, FakeItem(3, "sight", TOKYO_TOWER),
                 FakeItem(4, "sight", FAR_AWAY)]
        result, *_ = self.run_legs(items, walk_matrix({"WALK": 5400}), navitime=NAVITIME_ROUTE)
        pairs = [(leg["from_item_id"], leg["to_item_id"]) for leg in result]
        self.assertNotIn((1, 2), pairs)  # 항공편 앞에는 구간이 없다
        self.assertIn((2, 3), pairs)  # 항공편 다음 카드는 도착 공항에서 출발한다
        self.assertNotIn((3, 4), pairs)  # 지원 지역 밖은 표시하지 않는다

    def test_without_routes_key_returns_nothing(self):
        items = [FakeItem(1, "sight", SHIBUYA), FakeItem(2, "sight", TOKYO_TOWER)]
        result, m, *_ = self.run_legs(items, walk_matrix({"WALK": 60}), env={"GOOGLE_ROUTES_API_KEY": ""})
        self.assertEqual(result, [])
        m.assert_not_called()


class DayLegsApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="legs@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2030-01-07", end_date="2030-01-08", itinerary_initialized=True)
        for order, (title, point) in enumerate((("시부야", SHIBUYA), ("도쿄타워", TOKYO_TOWER))):
            ItineraryItem.objects.create(trip=self.trip, day="2030-01-07", order=order, kind="sight", source="manual",
                                         title=title, stops=[{"kind": "place", "caption": "주소", "label": title,
                                                              "lat": point[0], "lng": point[1]}])

    def get(self, day="2030-01-07"):
        with mock.patch.dict("os.environ", {"GOOGLE_ROUTES_API_KEY": "k", "NAVITIME_RAPIDAPI_KEY": "k"}), \
                mock.patch("trips.routes.travel_matrix", side_effect=walk_matrix({"WALK": 5400})), \
                mock.patch("trips.transit._request", return_value=(NAVITIME_ROUTE, 400)):
            return self.client.get(f"/api/v1/trips/{self.trip.pk}/days/{day}/legs/")

    def test_returns_legs_in_saved_order(self):
        response = self.get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first, second = list(self.trip.itinerary_items.order_by("order"))
        self.assertEqual([(l["from_item_id"], l["to_item_id"], l["mode"]) for l in response.data],
                         [(first.id, second.id, "transit")])

    def test_empty_day_and_validation_and_access(self):
        self.assertEqual(self.get("2030-01-08").data, [])
        self.assertEqual(self.get("2031-01-01").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.get("not-a-date").status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(User.objects.create_user(username="other@example.com"))
        self.assertEqual(self.get().status_code, status.HTTP_404_NOT_FOUND)


class KoreanLineNameTests(SimpleTestCase):
    def test_major_lines(self):
        from ..line_names import korean_line_name as ko
        cases = {
            "ＪＲ山手線": "JR야마노테선",  # 전각 ＪＲ도 처리
            "JR中央・総武線": "JR주오·소부선",
            "ＪＲ京浜東北線": "JR게이힌도호쿠선",
            "ＪＲ湘南新宿ライン": "JR쇼난신주쿠 라인",
            "東京メトロ半蔵門線": "도쿄메트로 한조몬선",
            "東京メトロ銀座線": "도쿄메트로 긴자선",
            "都営大江戸線": "도에이 오에도선",
            "都営三田線": "도에이 미타선",
            "東急東横線": "도큐 도요코선",
            "小田急小田原線": "오다큐 오다와라선",
            "京王井の頭線": "게이오 이노카시라선",
            "京成本線": "게이세이 본선",
            "東武東京スカイツリーライン": "도부 도쿄 스카이트리 라인",
            "つくばエクスプレス": "쓰쿠바 익스프레스",
            "ゆりかもめ": "유리카모메",
            "大阪メトロ御堂筋線": "오사카메트로 미도스지선",
            "ＪＲ東海道新幹線": "JR도카이도 신칸센",
            "ＪＲ大阪環状線": "JR오사카 환상선",
        }
        for japanese, korean in cases.items():
            self.assertEqual(ko(japanese), korean, japanese)

    def test_buses(self):
        from ..line_names import korean_line_name as ko
        self.assertEqual(ko("都営バス 渋88"), "도에이버스 渋88")  # 노선 번호·행선지는 그대로
        self.assertEqual(ko("東急バス"), "도큐버스")
        self.assertEqual(ko("名もなきバス"), "名もなき버스")

    def test_unknown_names_stay_as_is_and_empty_is_empty(self):
        from ..line_names import korean_line_name as ko
        self.assertEqual(ko("ＪＲ謎線"), "JR謎線")  # 사전에 없으면 원문(전각만 정리)
        self.assertEqual(ko("未知鉄道ほげ線"), "未知鉄道ほげ線")
        self.assertEqual(ko(""), "")
        self.assertEqual(ko(None), "")


class TrainTypeAndNormalizationTests(SimpleTestCase):
    def test_train_types_are_separated_from_line_names(self):
        from ..line_names import korean_line_and_type as split

        cases = {
            ("ＪＲ京都線新快速", "快速"): ("JR교토선", "JR京都線", "신쾌속", "新快速"),
            ("ＪＲ中央線快速", "快速"): ("JR주오선", "JR中央線", "쾌속", "快速"),
            ("ＪＲ京浜東北線・根岸線快速", "普通"): ("JR게이힌도호쿠선·네기시선", "JR京浜東北線・根岸線", "쾌속", "快速"),
            ("東京モノレール空港快速", "快速"): ("도쿄모노레일", "東京モノレール", "공항쾌속", "空港快速"),
            ("京成スカイライナー", "特急"): ("게이세이 스카이라이너", "京成スカイライナー", "특급", "特急"),  # 이름에 종별이 없으면 transport.type
            ("ＪＲ山手線", "普通"): ("JR야마노테선", "JR山手線", "", ""),  # 보통은 보여주지 않는다
            ("OsakaMetro御堂筋線", "普通"): ("오사카메트로 미도스지선", "OsakaMetro御堂筋線", "", ""),
            ("ＪＲ関空快速", "快速"): ("JR간쿠 쾌속", "JR関空快速", "쾌속", "快速"),  # 사전에 통째로 있는 이름은 종별을 떼지 않는다
        }
        for (name, declared), (line_ko, line_ja, type_ko, type_ja) in cases.items():
            result = split(name, declared)
            self.assertEqual((result["line_name"], result["line_name_ja"]), (line_ko, line_ja), name)
            self.assertEqual((result["train_type"], result["train_type_ja"]), (type_ko, type_ja), name)

    def test_unknown_line_keeps_original_and_only_known_type(self):
        from ..line_names import korean_line_and_type as split

        result = split("ＪＲ謎線快速", "快速")
        self.assertEqual((result["line_name"], result["train_type"]), ("JR謎線", "쾌속"))  # 노선은 원어, 종별은 확정된 값

    def test_compound_lines_need_every_part(self):
        from ..line_names import korean_line_name as ko

        self.assertEqual(ko("ＪＲ京浜東北線・根岸線"), "JR게이힌도호쿠선·네기시선")
        self.assertEqual(ko("ＪＲ京浜東北線・謎線"), "JR京浜東北線・謎線")  # 하나라도 모르면 원어 전체
