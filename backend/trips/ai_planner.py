"""
'AI와 함께 만들기': 대화로 받은 요청을 일정 변경 제안으로 바꾼다.

Claude(claude-sonnet-5)는 '어느 날, 어떤 장소, 몇 시'만 정한다(구조화된 응답).
순서·거리는 계산하지 않는다 - 실제 장소 확정(Google Places)과 배치(itinerary_planner)는 서버가 한다.
"""

import os
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-sonnet-5"
MAX_TOKENS = 16000


class PlanAddition(BaseModel):
    name: str = Field(description="장소 이름 (한국어로 널리 쓰는 이름)")
    search_query: str = Field(description="Google 지도 검색어. 장소 이름 + 도시 (예: '도쿄 스카이트리 도쿄')")
    kind: Literal["sight", "restaurant", "cafe", "hotel", "airport"]
    day_index: Optional[int] = Field(
        description="0부터 시작하는 날짜 번호. 사용자가 날짜를 말했거나 전체 계획을 짤 때만 정하고, 아니면 null"
    )
    time: Optional[str] = Field(description="'HH:MM'. 사용자가 시간을 말했거나 식사 시간처럼 분명할 때만, 아니면 null")
    reason: str = Field(description="이 장소를 고른 이유 한 문장")
    checklist: list[str] = Field(description="사전 예약·티켓 예매·준비물처럼 미리 챙길 것 (없으면 빈 목록)")


class PlanMove(BaseModel):
    item_id: int
    day_index: int
    time: Optional[str]


class PlanResponse(BaseModel):
    reply: str = Field(description="사용자에게 보여줄 한국어 답변. 무엇을 바꾸자고 제안하는지 짧게 설명")
    additions: list[PlanAddition]
    remove_item_ids: list[int] = Field(description="현재 일정에서 뺄 항목 id (사용자가 빼 달라고 한 것만)")
    moves: list[PlanMove] = Field(description="다른 날·시간으로 옮길 현재 일정 항목")


SYSTEM_PROMPT = """당신은 여행 계획 서비스 PinRoute의 여행 플래너입니다.
사용자의 여행 정보와 현재 일정을 보고, 사용자의 요청을 일정 변경 제안으로 바꿉니다.

- 장소는 실제로 존재하는 구체적인 장소만 고르세요 (지점이 여럿이면 지점명까지). search_query는 Google 지도에서
  그 장소 하나가 검색되도록 장소 이름과 도시를 함께 적으세요.
- 방문 순서와 동선은 서비스가 거리 기준으로 정합니다. 순서를 정하려 하지 말고, 장소·날짜·시간만 정하세요.
  - 사용자가 날짜를 말하면 그 day_index를, 시간을 말하면 time을 정하세요. 말하지 않았으면 null로 두세요.
  - 전체 계획을 짜 달라고 하면 하루에 3~4곳(출국·귀국일은 1~2곳)을 고르고, 같은 날에는 서로 가까운 동네의
    장소를 묶어 day_index를 정하세요. 숙소가 있으면 그 주변을 우선하세요.
- 현재 일정에 이미 있는 장소는 다시 추가하지 마세요. 빼거나 옮길 때는 현재 일정에 있는 id만 쓰세요.
- 사전 예약·티켓 예매가 필요한 곳이면 checklist에 "웹으로 티켓 사전 예매"처럼 짧게 적으세요.
- reply는 친근한 한국어로 2~4문장. 무엇을 추가·이동·삭제하자고 제안하는지 설명하세요.
- 일정 변경과 관계없는 질문에는 reply로만 답하고 나머지는 빈 목록으로 두세요."""


class PlannerError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def trip_context(trip, days, items_by_day):
    """현재 여행·일정을 모델에 줄 텍스트로 정리한다."""
    lines = [
        f"여행지: {trip.destination_label}",
        f"기간: {trip.start_date} ~ {trip.end_date} ({trip.nights}박 {trip.nights + 1}일)",
    ]
    hotels = [f"{h.name} ({h.check_in}~{h.check_out or '?'})" for h in trip.hotels.all()]
    if hotels:
        lines.append("숙소: " + ", ".join(hotels))
    lines.append("현재 일정:")
    for index, day in enumerate(days):
        cards = items_by_day.get(day, [])
        entries = ", ".join(
            f"[id={c['id']}] {c['title']}" + (f" {c['time']}" if c.get("time") else "")
            + (f" ({c['time_label']})" if c.get("time_label") else "")
            for c in cards
        ) or "없음"
        lines.append(f"- day_index {index} ({day}): {entries}")
    return "\n".join(lines)


def propose(trip, days, items_by_day, conversation):
    """
    conversation: [{"role": "user"|"assistant", "content": str}, ...] (마지막은 사용자 메시지)
    가장 최근 사용자 메시지 앞에 현재 여행 정보를 붙여 보낸다(적용 후 바뀐 일정을 반영하려고).
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise PlannerError("AI 키(ANTHROPIC_API_KEY)가 설정되지 않았어요.", status_code=503)

    messages = [{"role": turn["role"], "content": turn["content"]} for turn in conversation]
    context = trip_context(trip, days, items_by_day)
    messages[-1] = {
        "role": "user",
        "content": f"<current_trip>\n{context}\n</current_trip>\n\n{messages[-1]['content']}",
    }

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
            output_format=PlanResponse,
        )
    except anthropic.AuthenticationError as exc:
        raise PlannerError("AI 키가 올바르지 않아요.", status_code=503) from exc
    except anthropic.RateLimitError as exc:
        raise PlannerError("AI 요청이 많아요. 잠시 후 다시 시도해 주세요.", status_code=429) from exc
    except anthropic.APIStatusError as exc:
        raise PlannerError("AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요.") from exc
    except anthropic.APIConnectionError as exc:
        raise PlannerError("AI 서버에 연결하지 못했어요.") from exc

    if response.stop_reason == "refusal":
        raise PlannerError("이 요청은 도와드리기 어려워요. 다르게 말씀해 주세요.", status_code=400)
    if response.parsed_output is None:
        raise PlannerError("AI 응답을 이해하지 못했어요. 다시 시도해 주세요.")
    return response.parsed_output
