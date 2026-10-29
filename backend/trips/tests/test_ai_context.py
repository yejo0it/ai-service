"""
'AI와 함께 만들기' 여행 컨텍스트(trip_context)의 일정 정보 보존

- 일정 id는 #으로 줄이고, day_index는 일차와 구분한다. 날짜·방문 순서·일정 id·이름·시간·시간 표기는 모두 보낸다
  (압축한 문자열에서 모든 값을 다시 읽어 낼 수 있다).
- 표시한 id(#숫자)로 모델이 삭제·이동을 고르면 서버가 기존과 같이 이 여행의 일정 id만 받아들인다.
- 매 요청 DB에서 최신 일정을 읽어 보내므로 채팅 밖에서 바뀐 일정(직접 수정·일행)도 다음 요청에 반영된다.
- 항공·숙소 등록 정보와 적용 전 제안(draft) 표기는 그대로다.
"""

import os
import re
from datetime import date
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .. import ai_planner
from ..itinerary_views import days_map
from ..models import Hotel, ItineraryItem, Trip

User = get_user_model()

KEY = {"ANTHROPIC_API_KEY": "sk-ant-TEST-CONTEXT"}
DAY_LINE = re.compile(r"^day_index=(\d+) \(\d+일차, (\d{4}-\d{2}-\d{2})\): (.*)$")
ENTRY = re.compile(r"^#(\d+) (.+?)(?: (\d{2}:\d{2}))?(?: \(([^()]*)\))?$")


def parse_schedule(context):
    """압축한 '현재 일정'을 다시 읽는다: {day_index: (날짜, [(id, 이름, 시간, 시간 표기), ...])}"""
    schedule = {}
    for line in context.split("\n"):
        match = DAY_LINE.match(line)
        if not match:
            continue
        index, day, body = match.groups()
        entries = []
        if body != "없음":
            for part in body.split(", "):
                part = part.rsplit(" [", 1)[0]  # 종류·위치 메타데이터를 분리하고 원래 일정 필드를 복원한다.
                entry = ENTRY.match(part)
                assert entry, part
                card_id, title, time, label = entry.groups()
                entries.append((int(card_id), title, time or "", label or ""))
        schedule[int(index)] = (day, entries)
    return schedule


def plan(**changes):
    fields = dict(reply="정리했어요.", additions=[], remove_item_ids=[], moves=[], form=None, confirm=None,
                  flight=None, hotel_change=None, off_topic=False)
    fields.update(changes)
    return ai_planner.PlanResponse(**fields)


class CapturingMessages:
    """보낸 내용을 모아 두고 정해 둔 제안을 돌려주는 가짜 모델"""

    def __init__(self, result=None):
        self.result = result or plan()
        self.sent = []

    def parse(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=self.result, usage=None)


class TripContextFormatTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ctx@example.com", email="ctx@example.com")
        self.trip = Trip.objects.create(
            owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
            start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True,
            flight_info={"departure_airport": {"code": "ICN", "name": "인천국제공항"},
                         "arrival_airport": {"code": "NRT", "name": "나리타국제공항"},
                         "airline": "대한항공", "flight_number": "KE703", "departure_at": "2026-11-10T09:00"},
        )
        self.hotel = Hotel.objects.create(trip=self.trip, name="신주쿠 워싱턴 호텔", address="",
                                          check_in="2026-11-10", check_out="2026-11-12")
        rows = [
            ("2026-11-10", "flight", "가는 편 · KE703", "09:00", "출국"),
            ("2026-11-10", "sight", "센소지", None, ""),
            ("2026-11-10", "restaurant", "츠지한 니혼바시 본점 (2층)", "18:30", ""),
            ("2026-11-10", "hotel", "신주쿠 워싱턴 호텔", "15:00", "체크인"),
            ("2026-11-12", "hotel", "신주쿠 워싱턴 호텔", None, "체크아웃"),
            ("2026-11-12", "cafe", "블루보틀 아오야마", "10:00", ""),
        ]
        self.items = [
            ItineraryItem.objects.create(trip=self.trip, day=day, order=order, kind=kind, source="manual",
                                         title=title, time=time, time_label=label, stops=[])
            for order, (day, kind, title, time, label) in enumerate(rows)
        ]

    def context(self, draft=None):
        self.trip.refresh_from_db()
        days = days_map(self.trip)
        return ai_planner.trip_context(self.trip, sorted(days), days, draft)

    def test_every_field_is_kept_in_visit_order(self):
        context = self.context()
        expected = {}
        for index, day in enumerate(["2026-11-10", "2026-11-11", "2026-11-12"]):
            expected[index] = (day, [
                (item.id, item.title, item.time.strftime("%H:%M") if item.time else "", item.time_label)
                for item in ItineraryItem.objects.filter(trip=self.trip, day=day).order_by("order", "id")
            ])
        self.assertEqual(parse_schedule(context), expected)
        self.assertIn("day_index=1 (2일차, 2026-11-11): 없음", context)  # 빈 날짜도 인덱스·일차를 구분한다

    def test_registration_lines_are_unchanged(self):
        context = self.context()
        self.assertIn("기간: 2026-11-10 ~ 2026-11-12 (2박 3일)", context)
        self.assertIn("항공 등록 정보: 가는 편 인천국제공항 → 나리타국제공항 대한항공 KE703 (2026-11-10T09:00)", context)
        self.assertIn(f"숙소 등록 정보: [hotel_id={self.hotel.id}] 신주쿠 워싱턴 호텔 (2026-11-10~2026-11-12)", context)

    def test_draft_is_still_shown_as_pending(self):
        draft = {"hotels": [{"id": self.hotel.id, "name": "신주쿠 워싱턴 호텔", "check_in": date(2026, 11, 10),
                             "check_out": date(2026, 11, 11)},
                            {"id": None, "name": "시부야 스트림 엑셀 호텔", "check_in": date(2026, 11, 11),
                             "check_out": date(2026, 11, 12)}]}
        context = self.context(draft)
        self.assertIn("숙소 등록 정보 (이번 대화에서 제안한 내용 포함, 아직 적용 전):", context)
        self.assertIn("[새 숙소] 시부야 스트림 엑셀 호텔 (2026-11-11~2026-11-12)", context)

    def test_metadata_does_not_duplicate_ids_or_date_mapping(self):
        context = self.context()
        for item in self.items:
            self.assertEqual(len(re.findall(rf"#{item.id}\b", context)), 1)
        self.assertNotIn("날짜 대응:", context)
        self.assertNotIn("배치 정보 (", context)

    def test_system_prompt_explains_the_id_mark(self):
        self.assertIn("id(#뒤의 숫자)", ai_planner.SYSTEM_PROMPT)


class TripContextRequestTests(APITestCase):
    """요청 흐름: 최신 DB 일정 전달, 표시한 id로 삭제·이동, 서버 검증 유지"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="ctxflow@example.com", email="ctxflow@example.com")
        self.client.force_authenticate(self.user)
        self.trip = Trip.objects.create(owner=self.user, destinations=[{"city": "도쿄", "city_code": "tokyo"}],
                                        start_date="2026-11-10", end_date="2026-11-12", itinerary_initialized=True)
        self.first = ItineraryItem.objects.create(trip=self.trip, day="2026-11-10", order=0, kind="sight",
                                                  source="manual", title="센소지", stops=[])
        self.second = ItineraryItem.objects.create(trip=self.trip, day="2026-11-11", order=0, kind="sight",
                                                   source="manual", title="도쿄 타워", stops=[])
        other_trip = Trip.objects.create(owner=User.objects.create_user(username="x@example.com"),
                                         destinations=[], start_date="2026-11-10", end_date="2026-11-12")
        self.foreign = ItineraryItem.objects.create(trip=other_trip, day="2026-11-10", order=0, kind="sight",
                                                    source="manual", title="남의 일정", stops=[])

    def tearDown(self):
        cache.clear()

    def post(self, model, messages):
        with mock.patch.dict(os.environ, KEY), \
                mock.patch("trips.ai_planner.anthropic.Anthropic", return_value=SimpleNamespace(messages=model)):
            return self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/propose/", {"messages": messages}, format="json")

    def shown_ids(self, sent):
        context = sent["messages"][-1]["content"].split("</current_trip>")[0]
        return {card_id for _, entries in parse_schedule(context).values() for card_id, *_ in entries}

    def test_shown_ids_drive_remove_and_move_and_server_still_validates(self):
        model = CapturingMessages(plan(
            remove_item_ids=[self.first.id, self.foreign.id, 999999],
            moves=[ai_planner.PlanMove(item_id=self.second.id, day_index=2, time="15:00"),
                   ai_planner.PlanMove(item_id=self.foreign.id, day_index=0, time=None),
                   ai_planner.PlanMove(item_id=self.second.id, day_index=9, time=None)],
        ))
        response = self.post(model, [{"role": "user", "content": "센소지 빼고 도쿄 타워는 셋째 날 오후 3시로 옮겨줘"}])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.shown_ids(model.sent[0]), {self.first.id, self.second.id})
        proposal = response.data["proposal"]
        # 이 여행에 없는 id·여행 기간 밖 날짜는 기존처럼 서버가 버린다
        self.assertEqual(proposal["remove_item_ids"], [self.first.id])
        self.assertEqual([(m["item_id"], str(m["day"]), m["time"]) for m in proposal["moves"]],
                         [(self.second.id, "2026-11-12", "15:00")])
        applied = self.client.post(f"/api/v1/trips/{self.trip.pk}/ai/apply/", {"proposal": proposal}, format="json")
        self.assertEqual(applied.status_code, status.HTTP_200_OK)
        self.assertFalse(ItineraryItem.objects.filter(pk=self.first.pk).exists())
        moved = ItineraryItem.objects.get(pk=self.second.pk)
        self.assertEqual((str(moved.day), moved.time.strftime("%H:%M")), ("2026-11-12", "15:00"))
        self.assertTrue(ItineraryItem.objects.filter(pk=self.foreign.pk).exists())

    def test_each_request_reads_the_latest_schedule(self):
        """채팅 밖에서(직접 수정·일행) 바뀐 일정도 다음 요청의 컨텍스트에 그대로 들어간다."""
        model = CapturingMessages()
        first_id = self.first.id
        self.post(model, [{"role": "user", "content": "일정 봐줘"}])
        added = ItineraryItem.objects.create(trip=self.trip, day="2026-11-12", order=0, kind="cafe", source="manual",
                                             title="블루보틀 아오야마", stops=[])
        self.first.delete()
        self.post(model, [{"role": "user", "content": "일정 봐줘"}, {"role": "assistant", "content": "정리했어요."},
                          {"role": "user", "content": "그럼 마지막 날은?"}])
        self.assertEqual(self.shown_ids(model.sent[0]), {first_id, self.second.id})
        self.assertEqual(self.shown_ids(model.sent[1]), {self.second.id, added.id})
        # 후속 질문: 여행 정보는 마지막 사용자 메시지에만 붙고, 이전 대화는 그대로 보낸다
        messages = model.sent[1]["messages"]
        self.assertEqual([m["content"] for m in messages[:2]], ["일정 봐줘", "정리했어요."])
        self.assertEqual(sum(m["content"].count("<current_trip>") for m in messages), 1)
        self.assertTrue(messages[-1]["content"].endswith("그럼 마지막 날은?"))
