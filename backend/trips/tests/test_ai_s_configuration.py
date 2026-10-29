"""실제 평가에서 보존한 S 요청과 서비스 입력을 모델 호출 없이 대조한다."""

from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from .. import ai_planner


class SimpleOptimizationTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture = json.loads(
            (Path(__file__).resolve().parent.parent / "fixtures").joinpath("ai_planner_s_requests.json").read_text(encoding="utf-8")
        )

    def dataset(self, name):
        data = deepcopy(self.fixture["datasets"][name])
        hotels = [SimpleNamespace(**hotel) for hotel in data["trip"].pop("hotels")]
        trip = SimpleNamespace(**data["trip"], hotels=SimpleNamespace(all=lambda: hotels))
        trip.start_date = date.fromisoformat(trip.start_date)
        trip.end_date = date.fromisoformat(trip.end_date)
        cards = {date.fromisoformat(day): items for day, items in data["days"].items()}
        return trip, sorted(cards), cards

    def test_service_requests_match_all_evaluated_s_snapshots(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"]):
                trip, days, cards = self.dataset(case["dataset"])
                model = mock.Mock()
                model.parse.return_value = SimpleNamespace(
                    stop_reason="end_turn", usage=None,
                    parsed_output=ai_planner.PlanResponse(
                        reply="확인했어요.", additions=[], remove_item_ids=[], moves=[], form=None,
                        confirm=None, flight=None, hotel_change=None, off_topic=False,
                    ),
                )
                with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-TEST-SNAPSHOT"}), \
                        mock.patch("trips.ai_planner.anthropic.Anthropic",
                                   return_value=SimpleNamespace(messages=model)):
                    ai_planner.propose(trip, days, cards, deepcopy(case["conversation"]), source="evaluation")
                model.parse.assert_called_once()
                sent = model.parse.call_args.kwargs
                self.assertEqual(sent["system"], self.fixture["system"])
                self.assertEqual(sent["messages"], case["messages"])
                self.assertEqual(sent["model"], self.fixture["model"])
                self.assertEqual(sent["max_tokens"], self.fixture["max_tokens"])
                self.assertEqual(sent["output_format"].model_json_schema(), self.fixture["schema"])
                request = {"system": sent["system"], "messages": sent["messages"]}
                digest = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                self.assertEqual(digest, case["request_sha256"])
                self.assertTrue(case["evaluation_call_ids"])

    def test_compressed_context_retains_dates_ids_locations_and_stays(self):
        for name in self.fixture["datasets"]:
            with self.subTest(dataset=name):
                trip, days, cards = self.dataset(name)
                context = ai_planner.trip_context(trip, days, cards)
                for index, day in enumerate(days):
                    self.assertIn(f"day_index={index} ({index + 1}일차, {day}):", context)
                    for card in cards[day]:
                        self.assertEqual(context.count(f"#{card['id']} "), 1)
                        self.assertIn(f"[{card['kind']};", context)
                        self.assertIn(f";{card['stay_minutes']}m]", context)
                        for stop in card["stops"]:
                            if stop.get("lat") is not None and stop.get("lng") is not None:
                                self.assertIn(f"({stop['lat']:.3f},{stop['lng']:.3f})", context)
                hotel = trip.hotels.all()[0]
                self.assertIn(f"[hotel_id={hotel.id}] {hotel.name} ({hotel.check_in}~{hotel.check_out})", context)
                self.assertIn(f"({hotel.latitude:.3f},{hotel.longitude:.3f})", context)
                if name == "missing":
                    self.assertIn("sight;미상;60m", context)
