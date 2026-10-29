"""역·출구·운영사 이름의 한국어 표기(trips.station_names) 테스트. 역 데이터는 몇 개만 주입한다."""

from unittest import mock

from django.test import SimpleTestCase

from .. import station_names as sn

INDEX = {
    "渋谷": [(35.6585, 139.7013, "시부야역")],
    "日暮里": [(35.7276, 139.7708, "닛포리역")],
    "目黒": [(35.6340, 139.7160, "메구로역")],
    "青山一丁目": [(35.6729, 139.7243, "아오야마 1초메 역")],  # 데이터의 띄어쓰기 변형은 정리한다
    "赤羽橋": [(35.6550, 139.7436, "아카바네바시역")],
    "大手町": [(33.8397, 132.7550, "오테마치역")],  # 에히메현의 같은 이름 역만 있는 경우
    "大町": [(36.5, 137.8, "오마치역"), (35.0, 135.0, "다이마치역")],  # 이름이 같고 읽기가 다른 역
}


def data(index=INDEX, overrides=None):
    return (mock.patch("trips.station_names._load_index", return_value=index),
            mock.patch("trips.station_names._load_overrides", return_value=overrides or {}))


class KoreanStationTests(SimpleTestCase):
    def setUp(self):
        for patcher in data():
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_major_stations(self):
        self.assertEqual(sn.korean_station("渋谷", 35.65864, 139.70206), "시부야역")
        self.assertEqual(sn.korean_station("日暮里", 35.7276, 139.7708), "닛포리역")
        self.assertEqual(sn.korean_station("目黒", 35.634082, 139.715901), "메구로역")
        self.assertEqual(sn.korean_station("青山一丁目"), "아오야마 1초메역")

    def test_name_variants(self):
        for name in ("渋谷駅", "渋谷(東京都)", " 渋谷 "):
            self.assertEqual(sn.korean_station(name), "시부야역", name)

    def test_far_or_ambiguous_matches_are_rejected(self):
        # 도쿄의 大手町는 데이터에 없고 에히메의 항목만 있으면 연결하지 않는다.
        self.assertIsNone(sn.korean_station("大手町", 35.6867, 139.7639))
        self.assertEqual(sn.korean_station("大手町", 33.84, 132.755), "오테마치역")
        # 읽기가 다른 같은 이름은 좌표 없이 고르지 않는다.
        self.assertIsNone(sn.korean_station("大町"))
        self.assertEqual(sn.korean_station("大町", 36.5, 137.8), "오마치역")

    def test_unregistered_station_keeps_original(self):
        self.assertIsNone(sn.korean_station("謎"))
        self.assertEqual(sn.station_labels("謎"), ("謎駅", "謎駅"))
        self.assertEqual(sn.display_station("謎"), "謎駅")
        self.assertEqual(sn.display_station("渋谷", 35.65864, 139.70206), "시부야역(渋谷駅)")

    def test_node_id_override_wins(self):
        for patcher in data(overrides={"00003544": "시부야(검증)역"}):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.assertEqual(sn.korean_station("渋谷", node_id="00003544"), "시부야(검증)역")


class KoreanGatewayTests(SimpleTestCase):
    def setUp(self):
        for patcher in data():
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_direction_and_number_rules(self):
        cases = {
            "東口": "동쪽 출구", "西口": "서쪽 출구", "南口": "남쪽 출구", "北口": "북쪽 출구", "中央口": "중앙 출구",
            "中央東口": "중앙 동쪽 출구", "正面口": "정면 출구", "A1口": "A1 출구", "B2口": "B2 출구",
            "1番口": "1번 출구", "12番口": "12번 출구", "3口": "3 출구", "Ａ１口": "A1 출구",  # 전각도 정리
        }
        for japanese, korean in cases.items():
            self.assertEqual(sn.korean_gateway(japanese), korean, japanese)

    def test_station_named_exit_only_when_station_is_verified(self):
        self.assertEqual(sn.korean_gateway("赤羽橋口"), "아카바네바시 출구")
        self.assertEqual(sn.korean_gateway("謎橋口"), "謎橋口")  # 확인하지 못하면 원어 그대로
        self.assertEqual(sn.korean_gateway("改札内"), "改札内")
        self.assertEqual(sn.korean_gateway(""), "")


class KoreanCompanyTests(SimpleTestCase):
    def test_companies(self):
        self.assertEqual(sn.korean_company("ＪＲ東日本"), "JR동일본")
        self.assertEqual(sn.korean_company("東京地下鉄"), "도쿄메트로")
        self.assertEqual(sn.korean_company("東京都交通局"), "도쿄도교통국(도에이)")
        self.assertEqual(sn.korean_company("未知鉄道"), "未知鉄道")
        self.assertEqual(sn.korean_company(""), "")

    def test_parentheses_fullwidth_and_multiple_operators(self):
        self.assertEqual(sn.korean_company("東京地下鉄（メトロ）"), "도쿄메트로")  # 전각 괄호 설명을 뗀다
        self.assertEqual(sn.korean_company("北総鉄道/京成電鉄(成田空港線)"), "호쿠소철도/게이세이전철")  # 복수 운영사
        self.assertEqual(sn.korean_company("大阪市高速電気軌道"), "오사카메트로")
        self.assertEqual(sn.korean_company("東京地下鉄/謎鉄道"), "東京地下鉄/謎鉄道")  # 하나라도 모르면 원어 전체


class OverrideAndBracketTests(SimpleTestCase):
    def test_overrides_come_first_and_accept_object_values(self):
        patchers = [
            mock.patch("trips.station_names._load_index", return_value={"渋谷": [(35.6585, 139.7013, "시부야역")]}),
            mock.patch("trips.station_names._load_overrides", return_value={"00009396": "하네다공항 제1터미널역"}),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.assertEqual(sn.korean_station("羽田空港第１ターミナル（モノレール）", node_id="00009396"), "하네다공항 제1터미널역")
        self.assertEqual(sn.korean_station("渋谷", 35.65864, 139.70206, node_id="다른 id"), "시부야역")  # 예외 목록에 없으면 데이터
        self.assertIsNone(sn.korean_station("羽田空港第１ターミナル（モノレール）"))  # node_id가 없으면 추측하지 않는다

    def test_override_file_format_and_verified_entry(self):
        sn._load_overrides.cache_clear()
        overrides = sn._load_overrides()
        self.assertEqual(overrides.get("00009396"), "하네다공항 제1터미널역")
        self.assertNotIn("_note", overrides)

    def test_bracket_variants_are_stripped(self):
        with mock.patch("trips.station_names._load_index", return_value={"なんば": [(34.66, 135.50, "난바역")]}), \
                mock.patch("trips.station_names._load_overrides", return_value={}):
            self.assertEqual(sn.korean_station("なんば〔Osaka Metro〕"), "난바역")
            self.assertEqual(sn.korean_station("なんば（大阪市）"), "난바역")


class DataFileTests(SimpleTestCase):
    """저장소에 들어 있는 실제 데이터 파일(Wikidata)과 기본 설정."""

    def setUp(self):
        sn._load_index.cache_clear()
        self.addCleanup(sn._load_index.cache_clear)

    def test_enabled_by_default_and_disable_switch(self):
        from django.test import override_settings

        self.assertTrue(sn._load_index())  # 기본은 켜져 있고 파일을 읽는다
        with override_settings(STATION_NAMES_ENABLED=False):
            sn._load_index.cache_clear()
            self.assertEqual(sn._load_index(), {})  # 환경변수 STATION_NAMES_ENABLED=0으로 끌 수 있다
            self.assertIsNone(sn.korean_station("渋谷", 35.65864, 139.70206))

    def test_major_stations_from_the_real_file(self):
        self.assertEqual(sn.korean_station("渋谷", 35.65864, 139.70206), "시부야역")
        self.assertEqual(sn.korean_station("日暮里", 35.7276, 139.7708), "닛포리역")
        self.assertEqual(sn.korean_station("目黒", 35.634082, 139.715901), "메구로역")
        self.assertEqual(sn.korean_station("青山一丁目", 35.6729, 139.7243), "아오야마 1초메역")

    def test_flagged_entries_are_not_used(self):
        self.assertIsNone(sn.korean_station("京阪大津京"))  # '오지야마 역'으로 잘못 붙은 항목(읽기 의심 flag)
        self.assertIsNone(sn.korean_station("国府", 34.0, 134.0))
