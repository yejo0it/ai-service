"""한국어로 바꾸지 못한 역·노선 이름 수집(trips.untranslated)과 `manage.py untranslated_names` 테스트."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from . import legs, untranslated
from .test_legs import NAVITIME_ROUTE, with_station_data


class LogTestCase(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "logs" / "untranslated_names.jsonl"
        overrides = override_settings(TESTING=False, UNTRANSLATED_LOG_ENABLED=True, UNTRANSLATED_LOG_PATH=str(self.path))
        overrides.enable()
        self.addCleanup(overrides.disable)
        untranslated.reset()
        self.addCleanup(untranslated.reset)

    def lines(self):
        for handler in untranslated.logging.getLogger(untranslated.LOGGER_NAME).handlers:
            handler.flush()
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()] if self.path.exists() else []


class RecordTests(LogTestCase):
    def test_station_record_has_only_identifying_fields(self):
        untranslated.record_station("なかもず", "00012345", 34.5555555, 135.5)
        (record,) = self.lines()
        self.assertEqual({k: v for k, v in record.items() if k != "t"},
                         {"kind": "station", "name": "なかもず", "node_id": "00012345", "lat": 34.55556, "lng": 135.5})
        self.assertTrue(record["t"].endswith("Z"))

    def test_destination_has_name_only_and_line_has_operator(self):
        untranslated.record_station("なかもず")
        untranslated.record_line("謎鉄道謎線", "謎鉄道")
        station, line = self.lines()
        self.assertEqual(set(station), {"t", "kind", "name"})
        self.assertEqual({k: v for k, v in line.items() if k != "t"}, {"kind": "line", "name": "謎鉄道謎線", "operator": "謎鉄道"})

    def test_same_name_is_logged_once_per_process(self):
        for _ in range(3):
            untranslated.record_station("なんば〔Osaka Metro〕", "00001", 34.66, 135.5)
        untranslated.record_station("なんば〔Osaka Metro〕", "00002", 34.67, 135.5)  # 이름이 같아도 다른 역(node_id)은 따로
        self.assertEqual([line["node_id"] for line in self.lines()], ["00001", "00002"])

    def test_empty_names_are_ignored(self):
        untranslated.record_station("  ")
        untranslated.record_line("")
        self.assertEqual(self.lines(), [])

    def test_can_be_disabled_and_is_silent_during_tests(self):
        with override_settings(UNTRANSLATED_LOG_ENABLED=False):
            untranslated.record_station("なかもず")
        with override_settings(TESTING=True):
            untranslated.record_station("なかもず2")
        self.assertFalse(self.path.exists())

    def test_unwritable_location_never_raises(self):
        blocker = Path(self.dir.name) / "blocker"
        blocker.write_text("파일이라 폴더를 만들 수 없다", encoding="utf-8")
        with override_settings(UNTRANSLATED_LOG_PATH=str(blocker / "logs" / "x.jsonl")):
            untranslated.reset()
            untranslated.record_station("なかもず")  # 예외 없이 건너뛴다


class ParseIntegrationTests(LogTestCase):
    def test_only_unconverted_names_are_collected_from_a_route(self):
        # 시부야·메구로·시나가와만 데이터에 있고 오나리몬과 행선지(西高島平), 도에이 미타선 등은 없다고 가정
        index = {"渋谷": [(35.6585, 139.7013, "시부야역")], "目黒": [(35.6340, 139.7160, "메구로역")],
                 "品川": [(35.6286, 139.7392, "시나가와역")]}
        with with_station_data(index):
            legs.parse_navitime(NAVITIME_ROUTE, with_times=True)
        records = self.lines()
        names = {(r["kind"], r["name"]) for r in records}
        self.assertIn(("station", "御成門"), names)  # 변환하지 못한 역(지점)
        self.assertIn(("station", "西高島平"), names)  # 변환하지 못한 행선지
        self.assertNotIn(("station", "渋谷"), names)  # 변환한 것은 남기지 않는다
        self.assertNotIn(("station", "目黒"), names)
        self.assertNotIn(("line", "ＪＲ山手線"), names)  # 노선은 사전에 있어 변환됨
        station = next(r for r in records if r["name"] == "御成門")
        self.assertEqual(station["node_id"], "00002292")  # 식별 정보: node_id와 좌표
        self.assertEqual((station["lat"], station["lng"]), (35.65942, 139.75045))
        for record in records:  # 그 밖의 정보(경로·시각·요금·사용자)는 기록하지 않는다
            self.assertLessEqual(set(record), {"t", "kind", "name", "node_id", "lat", "lng", "operator"})

    def test_unknown_line_is_collected_with_operator(self):
        payload = {"items": [{"summary": {"move": {"time": 5}}, "sections": [
            {"type": "move", "move": "local_train", "time": 5, "line_name": "謎鉄道謎線",
             "transport": {"name": "謎鉄道謎線", "company": {"name": "謎鉄道"}, "links": []}}]}]}
        with with_station_data({}):
            legs.parse_navitime(payload, True)
        line = next(r for r in self.lines() if r["kind"] == "line")
        self.assertEqual((line["name"], line["operator"]), ("謎鉄道謎線", "謎鉄道"))


class CommandTests(LogTestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("untranslated_names", *args, stdout=out)
        return out.getvalue()

    def write(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n깨진 줄\n", encoding="utf-8")

    def test_empty(self):
        self.assertIn("수집된 미변환 이름이 없습니다", self.run_command())

    def test_aggregates_counts_and_sorts(self):
        self.write([
            {"t": "2026-10-21T01:00:00Z", "kind": "station", "name": "なかもず", "node_id": "1", "lat": 34.5, "lng": 135.5},
            {"t": "2026-10-21T02:00:00Z", "kind": "station", "name": "なかもず", "node_id": "1", "lat": 34.5, "lng": 135.5},
            {"t": "2026-10-21T03:00:00Z", "kind": "station", "name": "なかもず", "node_id": "1", "lat": 34.5, "lng": 135.5},
            {"t": "2026-10-21T01:00:00Z", "kind": "line", "name": "謎鉄道謎線", "operator": "謎鉄道"},
        ])
        output = self.run_command()
        self.assertIn("미변환 이름 2건", output)
        first, second = [line for line in output.splitlines() if "회" in line][:2]
        self.assertIn("3회  [역] なかもず  node_id=1 좌표=34.5,135.5", first)  # 많이 나온 것이 먼저
        self.assertIn("1회  [노선] 謎鉄道謎線  운영사=謎鉄道", second)
        self.assertIn("마지막 2026-10-21T03:00:00Z", first)

    def test_kind_limit_and_json(self):
        self.write([{"t": "t", "kind": "station", "name": "A"}, {"t": "t", "kind": "line", "name": "B"},
                    {"t": "t", "kind": "line", "name": "C"}])
        self.assertNotIn("[역]", self.run_command("--kind", "line"))
        self.assertEqual(len([l for l in self.run_command("--limit", "1").splitlines() if "회" in l]), 1)
        rows = [json.loads(line) for line in self.run_command("--json").splitlines()]
        self.assertEqual(sorted(r["name"] for r in rows), ["A", "B", "C"])
        self.assertTrue(all("count" in r for r in rows))
