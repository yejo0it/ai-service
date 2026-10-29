"""
'AI와 함께 만들기' 구조화 응답 스키마(PlanResponse) 최적화

- 모델에 보내는 스키마에는 pydantic 자동 title이 없고, 설명은 짧은 영어다(한국어 답변 정책은 SYSTEM_PROMPT에 그대로).
- 쓰지 않던 PlanAddition.reason만 빠지고, 나머지 필드·필수 여부·타입·선택지(enum)는 그대로다.
- 모델 응답이 형식에 맞지 않으면 기존처럼 받아들이지 않는다.
"""

import os
import re
from types import SimpleNamespace
from unittest import mock

from anthropic.lib._parse._transform import transform_schema
from django.test import SimpleTestCase
from pydantic import TypeAdapter, ValidationError

from .. import ai_planner

HANGUL = re.compile(r"[가-힣]")

# 모델별 필드 (모두 필수: 구조화 출력은 값이 없을 때 null을 쓴다. source_ids만 기본값이 있다)
FIELDS = {
    "PlanResponse": ["reply", "additions", "remove_item_ids", "moves", "form", "confirm", "flight", "hotel_change",
                     "off_topic", "source_ids"],
    "PlanAddition": ["name", "search_query", "kind", "day_index", "time", "stay_minutes"],
    "PlanMove": ["item_id", "day_index", "time"],
    "FlightChange": ["mode", "outbound", "return_leg"],
    "FlightLegInput": ["departure_airport_code", "departure_airport_name", "arrival_airport_code",
                       "arrival_airport_name", "airline", "flight_number", "arrival_time", "date"],
    "HotelChange": ["mode", "hotels"],
    "HotelInput": ["hotel_id", "name", "search_query", "check_in", "check_out"],
}


def sent_schema():
    """SDK가 output_format으로 실제 보내는 스키마"""
    return transform_schema(TypeAdapter(ai_planner.PlanResponse).json_schema())


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


class SentSchemaTests(SimpleTestCase):
    def test_no_auto_titles_and_short_english_descriptions(self):
        schema = sent_schema()
        self.assertFalse([node for node in walk(schema) if "title" in node])
        descriptions = [node["description"] for node in walk(schema) if "description" in node]
        self.assertTrue(descriptions)
        self.assertFalse([d for d in descriptions if HANGUL.search(d)])
        self.assertTrue(all(len(d) <= 60 for d in descriptions), descriptions)

    def test_fields_and_required_are_kept_and_reason_is_gone(self):
        schema = sent_schema()
        models = {"PlanResponse": schema, **schema["$defs"]}
        self.assertEqual(set(models), set(FIELDS))
        for name, fields in FIELDS.items():
            with self.subTest(model=name):
                self.assertEqual(list(models[name]["properties"]), fields)
                self.assertEqual(set(models[name]["required"]), set(fields) - {"source_ids"})  # 변경 전과 같다
                self.assertFalse(models[name]["additionalProperties"])
        self.assertNotIn("reason", models["PlanAddition"]["properties"])

    def test_types_and_choices_are_kept(self):
        defs = sent_schema()["$defs"]
        self.assertEqual(defs["PlanAddition"]["properties"]["kind"]["enum"],
                         ["sight", "restaurant", "cafe", "hotel", "airport"])
        self.assertEqual(defs["FlightChange"]["properties"]["mode"]["enum"], ["update", "replace"])
        self.assertEqual(defs["HotelChange"]["properties"]["mode"]["enum"], ["update", "add"])
        self.assertEqual(defs["PlanMove"]["properties"]["item_id"], {"type": "integer"})
        top = sent_schema()["properties"]
        self.assertEqual(top["remove_item_ids"]["items"], {"type": "integer"})
        self.assertEqual(top["off_topic"]["type"], "boolean")

    def test_korean_reply_policy_stays_in_the_system_prompt(self):
        self.assertIn("reply는 친근한 한국어로", ai_planner.SYSTEM_PROMPT)
        self.assertIn("Korean", sent_schema()["properties"]["reply"]["description"])


class ModelOutputValidationTests(SimpleTestCase):
    def test_missing_or_wrong_fields_are_rejected(self):
        valid = {"reply": "좋아요", "additions": [], "remove_item_ids": [], "moves": [], "form": None, "confirm": None,
                 "flight": None, "hotel_change": None, "off_topic": False}
        ai_planner.PlanResponse.model_validate(valid)
        for broken in ({k: v for k, v in valid.items() if k != "reply"}, {**valid, "form": "train"},
                       {**valid, "remove_item_ids": ["abc"]},
                       {**valid, "additions": [{"name": "센소지", "search_query": "센소지 도쿄", "kind": "museum",
                                                "day_index": 0, "time": None, "stay_minutes": 60}]}):
            with self.subTest(broken=broken), self.assertRaises(ValidationError):
                ai_planner.PlanResponse.model_validate(broken)

    def test_unparsed_model_output_keeps_the_existing_error(self):
        client = SimpleNamespace(messages=SimpleNamespace(
            parse=lambda **kwargs: SimpleNamespace(stop_reason="end_turn", parsed_output=None, usage=None)))
        trip = SimpleNamespace(destination_label="도쿄", start_date="2026-11-10", end_date="2026-11-11", nights=1,
                               flight_info=None, hotels=SimpleNamespace(all=lambda: []))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-TEST"}), \
                mock.patch("trips.ai_planner.anthropic.Anthropic", return_value=client), \
                self.assertRaises(ai_planner.PlannerError) as caught:
            ai_planner.propose(trip, [], {}, [{"role": "user", "content": "일정 짜줘"}], source="user")
        self.assertEqual(str(caught.exception), "AI 응답을 이해하지 못했어요. 다시 시도해 주세요.")
