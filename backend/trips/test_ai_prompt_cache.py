"""
'AI와 함께 만들기' 프롬프트 캐싱 (ai_planner.SYSTEM_BLOCKS)

- 공통·재구성 상세 프롬프트의 고정 캐시 지점(cache_control, 기본 5분)은 모든 요청에서 유지한다.
- 대화·여행 정보·질문은 캐시 지점 뒤(messages)에 그대로 있어 매 요청 최신 DB 내용으로 새로 보낸다.
- 캐시 생성·적중·미적중의 usage가 그대로 기록되고, 미적중이어도 응답은 같다.
- 캐시와 관련한 API 오류는 기존 오류 응답으로 처리하고 다시 보내지 않는다(같은 옵션으로 반복 호출하지 않는다).
"""

import json
import os
from types import SimpleNamespace
from unittest import mock

import anthropic
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from . import ai_planner, ai_usage
from .models import ItineraryItem, Trip

User = get_user_model()

KEY = {"ANTHROPIC_API_KEY": "sk-ant-TEST-CACHE"}
FIXED = 10100  # 시스템 프롬프트(+스키마) 고정 부분이라고 가정한 토큰 수


def plan():
    return ai_planner.PlanResponse(reply="정리했어요.", additions=[], remove_item_ids=[], moves=[], form=None,
                                   confirm=None, flight=None, hotel_change=None, off_topic=False)


class FakeMessages:
    """보낸 요청을 모아 두고, 차례로 정해 둔 usage(또는 예외)를 돌려주는 가짜 모델"""

    def __init__(self, *usages):
        self.usages = list(usages)
        self.sent = []

    def parse(self, **kwargs):
        self.sent.append(kwargs)
        usage = self.usages.pop(0)
        if isinstance(usage, Exception):
            raise usage
        return SimpleNamespace(stop_reason="end_turn", parsed_output=plan(), usage=usage)


def usage(input_tokens=850, created=0, read=0, output_tokens=200):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                           cache_creation_input_tokens=created, cache_read_input_tokens=read)


def calls(logs):
    return [record for record in (json.loads(line.split(":", 2)[2]) for line in logs.output)
            if record["event"] == "claude_call"]


class PromptCacheTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="cache@example.com", email="cache@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True)
        ItineraryItem.objects.create(trip=self.trip, day="2026-11-10", order=0, kind="sight", source="manual",
                                     title="센소지", stops=[])

    def tearDown(self):
        cache.clear()

    def post(self, model, text="첫째 날 일정 봐줘"):
        with mock.patch.dict(os.environ, KEY), \
                mock.patch("trips.ai_planner.anthropic.Anthropic", return_value=SimpleNamespace(messages=model)):
            return self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                    {"messages": [{"role": "user", "content": text}]}, format="json")

    def test_request_keeps_both_fixed_system_cache_points(self):
        model = FakeMessages(usage(), usage())
        self.post(model, "환전 방법 알려줘")
        self.post(model, "준비물 알려줘")
        first, second = model.sent
        self.assertEqual(first["system"], [
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
            for prompt in (ai_planner.SYSTEM_PROMPT, ai_planner.REORGANIZATION_PROMPT)
        ])  # ttl 없음 = 기본 5분
        self.assertEqual(first["system"], second["system"])  # 고정 부분은 요청마다 똑같다
        self.assertIs(first["output_format"], ai_planner.PlanResponse)
        # 동적인 내용은 두 고정 시스템 블록 뒤(messages)에만 둔다.
        self.assertNotIn("센소지", first["system"][0]["text"])  # 여행 데이터는 캐시하는 블록에 없다
        for message in first["messages"]:
            self.assertIsInstance(message["content"], str)
        self.assertNotIn("cache_control", first)
        self.assertIn("<current_trip>", first["messages"][-1]["content"])

    def test_cache_write_hit_and_miss_are_logged_and_answers_are_the_same(self):
        model = FakeMessages(usage(created=FIXED), usage(read=FIXED), usage())
        with self.assertLogs(ai_usage.LOGGER_NAME, "INFO") as logs:
            replies = [self.post(model).data["reply"] for _ in range(3)]
        self.assertEqual(replies, ["정리했어요."] * 3)
        write, hit, miss = calls(logs)
        self.assertEqual((write["cache_creation_input_tokens"], write["cache_read_input_tokens"]), (FIXED, 0))
        self.assertEqual((hit["cache_creation_input_tokens"], hit["cache_read_input_tokens"]), (0, FIXED))
        self.assertEqual((miss["cache_creation_input_tokens"], miss["cache_read_input_tokens"]), (0, 0))
        # 전체 입력은 캐시 여부와 관계없이 같고(캐시는 단가만 바꾼다), 세 값을 한 번씩만 센다
        self.assertEqual({r["total_input_tokens"] for r in (write, hit)}, {FIXED + 850})
        self.assertTrue(all(r["success"] for r in (write, hit, miss)))

    def test_latest_schedule_is_sent_after_the_cache_point(self):
        model = FakeMessages(usage(created=FIXED), usage(read=FIXED))
        self.post(model)
        ItineraryItem.objects.create(trip=self.trip, day="2026-11-11", order=0, kind="sight", source="manual",
                                     title="도쿄 타워", stops=[])
        self.post(model)
        first, second = model.sent
        self.assertEqual(first["system"], second["system"])
        self.assertNotIn("도쿄 타워", first["messages"][-1]["content"])
        self.assertIn("도쿄 타워", second["messages"][-1]["content"])

    def test_cache_related_api_error_is_not_retried(self):
        response = mock.Mock(status_code=400, headers={})
        error = anthropic.BadRequestError("cache_control 오류", response=response, body=None)
        model = FakeMessages(error)
        with self.assertLogs(ai_usage.LOGGER_NAME, "INFO") as logs:
            result = self.post(model)
        self.assertEqual(result.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(result.data, {"detail": "AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요."})
        self.assertEqual(len(model.sent), 1)  # 캐시 없이 다시 보내지 않는다
        [record] = calls(logs)
        self.assertEqual((record["success"], record["error"]), (False, "BadRequestError"))
        self.assertNotIn("cache_control 오류", "\n".join(logs.output))  # 오류 메시지는 남기지 않는다
