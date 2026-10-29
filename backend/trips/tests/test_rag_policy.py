"""
'AI와 함께 만들기' 조건부 여행 정보 검색(RAG) (trips.rag_policy)

- 분명한 수정·등록 요청(삭제·시간 변경·날짜 간 이동·항공/숙소 정보·확인 선택지)만 검색을 건너뛴다.
- 추천·현지 정보·장소 추가·계획·재구성·복합·모호한 요청은 기존처럼 검색한다(애매하면 검색).
- 건너뛰면 프롬프트에 <reference_docs>가 없고 출처도 없다. 캐시 지점·응답 형식·검색 실패 처리는 그대로다.
- ai_request에 검색 여부·사유·문서 수·글자 수·검색 시간이 숫자·코드로만 남는다(질문 원문 없음).
"""

import json
import os
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from guides import search

from .. import ai_planner, ai_usage
from ..models import Trip
from ..rag_policy import guide_search_decision

User = get_user_model()

KEY = {"ANTHROPIC_API_KEY": "sk-ant-TEST-RAG"}

SKIP_CASES = {
    # 1. 기존 장소 삭제
    "첫째 날 나카미세 거리는 빼줘": "edit_only",
    "블루보틀 일정 삭제해줘": "edit_only",
    # 2. 시간 변경
    "센소지는 오전 10시로 바꿔줘": "edit_only",
    "이치란 우에노점은 12:30으로 변경": "edit_only",
    # 3. 날짜 간 이동
    "둘째 날 시부야 스카이를 넷째 날 저녁 7시로 옮겨줘": "edit_only",
    # 항공·숙소 정보 수정·등록
    "가는 편은 대한항공 KE703으로 인천에서 나리타 오전 11시 30분 도착이야": "edit_only",
    "KE704 도착 시간은 21시 15분이야": "edit_only",
    "체크아웃 12일로 바꿔줘": "edit_only",
    "숙소는 13일부터 15일까지 시부야 스트림 엑셀 호텔도 추가해줘": "registration",
    # 서버가 보여 준 확인 선택지
    "기존 정보 수정": "confirm_choice",
    "새로 입력(덮어쓰기)": "confirm_choice",
    "기본 정보 수정": "confirm_choice",
    "새로운 숙소 추가": "confirm_choice",
}
SEARCH_CASES = {
    # 4. 특정 장소 추가: 이름과 종류를 규칙으로 가리기 어려워 검색한다
    "셋째 날에 도쿄 스카이트리 넣어줘": "add_place",
    # 5. 관광지·음식점 추천
    "셋째 날 저녁에 도쿄 타워 근처 맛집 하나 추가해줘": "info",
    "도쿄에서 꼭 가볼 만한 곳 추천해줘": "info",
    # 6. 신규 일정 생성
    "전체 여행 계획 짜줘": "info",
    # 7. 기존 장소만 재배치하는 재구성(정확성 우선으로 검색)
    "전체 여행 경로를 동선 위주로 다시 짜줘": "info",
    # 8. 추천을 포함한 재구성
    "일정을 다시 짜고 가볼 만한 곳도 더 넣어줘": "info",
    # 9. 복합 요청
    "둘째 날 블루보틀은 빼고, 넷째 날 점심에 라멘집 하나 넣어줘": "info",
    "센소지 10시로 바꿔줘, 그때 문 열어?": "info",
    "센소지를 다른 곳으로 바꿔줘": "info",
    "호텔 옆에 카페 하나 넣어줘": "info",
    "다른 호텔로 바꿔줘": "info",
    # 현지 정보 질문
    "도쿄에서 교통카드 스이카 써야 해?": "info",
    "11월 도쿄 날씨는 어때": "info",
    # 10. 모호한 요청
    "그걸로 해줘": "default",
    "셋째 날 일정 비워줘": "default",
    "": "default",
}


class DecisionTests(SimpleTestCase):
    def test_clear_edits_and_registrations_skip_the_search(self):
        for text, reason in SKIP_CASES.items():
            with self.subTest(text=text):
                self.assertEqual(guide_search_decision(text), (False, reason))

    def test_recommendations_info_additions_plans_mixed_and_ambiguous_requests_search(self):
        for text, reason in SEARCH_CASES.items():
            with self.subTest(text=text):
                self.assertEqual(guide_search_decision(text), (True, reason))

    def test_confirm_choice_must_match_exactly(self):
        self.assertEqual(guide_search_decision("  기존 정보 수정  "), (False, "confirm_choice"))
        self.assertTrue(guide_search_decision("기존 정보 수정하고 맛집도 추천해줘")[0])


def plan(**changes):
    fields = dict(reply="정리했어요.", additions=[], remove_item_ids=[], moves=[], form=None, confirm=None,
                  flight=None, hotel_change=None, off_topic=False)
    fields.update(changes)
    return ai_planner.PlanResponse(**fields)


class FakeMessages:
    def __init__(self, result=None):
        self.result = result or plan()
        self.sent = []

    def parse(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=self.result, usage=None)


HIT = search.GuideHit(id=901, title="Japan", section="Buy > Tipping", content="Tipping is not customary in Japan.",
                      url="https://en.wikivoyage.org/wiki/Japan", license="CC BY-SA 4.0", similarity=0.84)


class ConditionalSearchRequestTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="rag@example.com", email="rag@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True)

    def tearDown(self):
        cache.clear()

    def post(self, text, model=None, hits=(HIT,)):
        model = model or FakeMessages()
        with mock.patch.dict(os.environ, KEY), \
                mock.patch("trips.ai_planner.anthropic.Anthropic", return_value=SimpleNamespace(messages=model)), \
                mock.patch("guides.search.search_for_trip", return_value=list(hits)) as searched, \
                self.assertLogs(ai_usage.LOGGER_NAME, "INFO") as logs:
            response = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                        {"messages": [{"role": "user", "content": text}]}, format="json")
        [record] = [r for r in (json.loads(line.split(":", 2)[2]) for line in logs.output) if r["event"] == "ai_request"]
        return response, record, model, searched, logs

    def test_edit_request_skips_search_and_sends_no_documents(self):
        response, record, model, searched, logs = self.post("첫째 날 나카미세 거리는 빼줘", FakeMessages(plan(source_ids=[901])))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        searched.assert_not_called()
        self.assertNotIn("<reference_docs>", model.sent[0]["messages"][-1]["content"])
        self.assertEqual(response.data["sources"], [])  # 보내지 않은 문서는 출처로 인정하지 않는다(기존 규칙)
        self.assertEqual({k: record[k] for k in ai_usage.RAG_FIELDS},
                         {"rag_used": False, "rag_reason": "edit_only", "rag_hits": 0, "rag_chars": 0, "rag_ms": None})
        self.assertNotIn("나카미세", "\n".join(logs.output))

    def test_recommendation_searches_and_keeps_documents_and_sources(self):
        response, record, model, searched, logs = self.post("일본 식당에서 팁 줘야 해?", FakeMessages(plan(source_ids=[901])))
        searched.assert_called_once()
        self.assertEqual(searched.call_args.args[1], "일본 식당에서 팁 줘야 해?")
        content = model.sent[0]["messages"][-1]["content"]
        self.assertIn("<reference_docs>", content)
        self.assertIn("Tipping is not customary", content)
        self.assertEqual([s["id"] for s in response.data["sources"]], [901])
        self.assertEqual((record["rag_used"], record["rag_reason"], record["rag_hits"]), (True, "info", 1))
        self.assertEqual(record["rag_chars"], len(ai_planner.reference_context([HIT])))
        self.assertIsInstance(record["rag_ms"], int)
        self.assertNotIn("팁 줘야", "\n".join(logs.output))

    def test_search_failure_keeps_the_existing_safe_fallback(self):
        model = FakeMessages()
        with mock.patch.dict(os.environ, KEY), \
                mock.patch("trips.ai_planner.anthropic.Anthropic", return_value=SimpleNamespace(messages=model)), \
                mock.patch("guides.search.search", side_effect=RuntimeError("db down")), \
                self.assertLogs(ai_usage.LOGGER_NAME, "INFO") as logs:
            response = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/",
                                        {"messages": [{"role": "user", "content": "도쿄 맛집 추천해줘"}]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("<reference_docs>", model.sent[0]["messages"][-1]["content"])
        [record] = [r for r in (json.loads(line.split(":", 2)[2]) for line in logs.output if "pinroute.ai_usage" in line)
                    if r["event"] == "ai_request"]
        self.assertEqual((record["rag_used"], record["rag_hits"]), (True, 0))

    def test_cache_point_and_response_shape_do_not_depend_on_the_search(self):
        model = FakeMessages()
        skipped, *_ = self.post("센소지는 오전 10시로 바꿔줘", model)
        # 같은 요청의 RAG 여부만 바꿔 비교한다. 두 고정 시스템 블록은 검색 여부와 무관하다.
        with mock.patch("trips.itinerary_views.rag_policy.guide_search_decision", return_value=(True, "default")):
            searched_response, *_ = self.post("센소지는 오전 10시로 바꿔줘", model)
        self.assertEqual(model.sent[0]["system"], model.sent[1]["system"])
        self.assertEqual(model.sent[0]["system"], ai_planner.SYSTEM_BLOCKS)
        self.assertEqual(set(skipped.data), set(searched_response.data))

    def test_mixed_request_searches(self):
        _, record, _, searched, _ = self.post("둘째 날 블루보틀은 빼고, 넷째 날 점심에 라멘집 하나 넣어줘")
        searched.assert_called_once()
        self.assertEqual(record["rag_reason"], "info")
