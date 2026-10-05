"""
'AI와 함께 만들기': 대화로 받은 요청을 일정 변경 제안으로 바꾼다.

Claude(claude-sonnet-5)는 '어느 날, 어떤 장소, 몇 시'만 정한다(구조화된 응답).
순서·거리는 계산하지 않는다 - 실제 장소 확정(Google Places)과 배치(itinerary_planner)는 서버가 한다.
항공·숙소 등록은 요청 종류(양식 안내·수정/덮어쓰기 확인·등록)만 고르고 받은 항목을 옮겨 적는다.
양식·확인 문구와 등록 정보 계산은 서버(registration)가 한다.
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


class FlightLegInput(BaseModel):
    """항공편 한 편. 사용자가 말하지 않은 항목은 null."""

    departure_airport_code: Optional[str] = Field(description="출발 공항 IATA 코드 (예: ICN)")
    departure_airport_name: Optional[str] = Field(description="출발 공항 한국어 이름 (예: 인천국제공항)")
    arrival_airport_code: Optional[str] = Field(description="도착 공항 IATA 코드 (예: NRT)")
    arrival_airport_name: Optional[str] = Field(description="도착 공항 한국어 이름 (예: 나리타국제공항)")
    airline: Optional[str] = Field(description="항공사 한국어 이름 (예: 대한항공)")
    flight_number: Optional[str] = Field(description="항공편명 (예: KE703)")
    arrival_time: Optional[str] = Field(description="도착 시각 'HH:MM' (사용자가 도착 시간을 말했을 때만)")
    date: Optional[str] = Field(description="'YYYY-MM-DD'. 사용자가 날짜를 말했을 때만")


class FlightChange(BaseModel):
    mode: Literal["update", "replace"] = Field(
        description="update: 말한 항목만 바꾸고 나머지는 유지 / replace: 기존 항공 정보를 지우고 이 정보로 새로 등록"
    )
    outbound: Optional[FlightLegInput] = Field(description="가는 날 항공편 (말하지 않았으면 null)")
    return_leg: Optional[FlightLegInput] = Field(description="오는 날 항공편 (말하지 않았으면 null)")


class HotelInput(BaseModel):
    hotel_id: Optional[int] = Field(description="수정할 기존 숙소의 hotel_id. 새 숙소면 null")
    name: Optional[str] = Field(description="숙소 이름 (바꾸거나 새로 등록할 때만)")
    search_query: Optional[str] = Field(description="Google 지도 검색어: 숙소 이름 + 도시 (이름이 있을 때만)")
    check_in: Optional[str] = Field(description="체크인 날짜 'YYYY-MM-DD' (말했을 때만)")
    check_out: Optional[str] = Field(description="체크아웃 날짜 'YYYY-MM-DD' (말했을 때만)")


class HotelChange(BaseModel):
    mode: Literal["update", "add"] = Field(
        description="update: hotel_id로 가리킨 기존 숙소의 말한 항목만 수정 / add: 기존 숙소는 그대로 두고 새 숙소를 추가"
    )
    hotels: list[HotelInput]


class PlanResponse(BaseModel):
    reply: str = Field(description="사용자에게 보여줄 한국어 답변. 무엇을 바꾸자고 제안하는지 짧게 설명")
    additions: list[PlanAddition]
    remove_item_ids: list[int] = Field(description="현재 일정에서 뺄 항목 id (사용자가 빼 달라고 한 것만)")
    moves: list[PlanMove] = Field(description="다른 날·시간으로 옮길 현재 일정 항목")
    form: Optional[Literal["flight", "hotel"]] = Field(
        description="항공(flight)·숙소(hotel) 입력 양식을 보여줄 때만. 아니면 null"
    )
    confirm: Optional[Literal["flight", "hotel"]] = Field(
        description="이미 등록된 항공·숙소를 어떻게 바꿀지(항공: 수정/덮어쓰기, 숙소: 수정/새 숙소 추가) 물어볼 때만. 아니면 null"
    )
    flight: Optional[FlightChange] = Field(description="항공 정보를 등록·수정할 때만. 아니면 null")
    hotel_change: Optional[HotelChange] = Field(description="숙소 정보를 등록·수정할 때만. 아니면 null")


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
- 일정 변경과 관계없는 질문에는 reply로만 답하고 나머지는 빈 목록으로 두세요.

항공·숙소 등록 (<current_trip>의 '항공 등록 정보'·'숙소 등록 정보'를 보고 판단하세요)
- 항공·숙소는 additions에 넣지 말고 flight·hotel_change로 다루세요.
- 등록되지 않은 항공(또는 숙소)을 등록하고 싶다고만 하고 구체적인 정보가 없으면 form="flight"(또는 "hotel")로
  두세요. 양식은 서비스가 보여줍니다.
- 이미 등록된 항공(또는 숙소)을 더하거나 바꾸려는데, 대화에서 아직 바꾸는 방법이 정해지지 않았다면 다른 변경 없이
  confirm="flight"(또는 "hotel")로 두세요. 확인 문구와 선택 버튼은 서비스가 보여줍니다.
  - 항공 선택지: '기존 정보 수정' / '새로 입력(덮어쓰기)'
  - 숙소 선택지: '기본 정보 수정' / '새로운 숙소 추가'
- 이번 대화에서 이미 방법을 골랐거나, 방금 등록·제안한 항공·숙소를 이어서 고치는 요청(예: "가는 날 도착 시간을
  오전 9시로 변경해줘")이면 다시 묻지 말고 mode="update"로 말한 항목만 채우세요. <current_trip>의 등록 정보에는
  아직 적용하지 않은 제안도 반영돼 있으니, 그 내용을 유지한 채 요청한 항목만 바꾸면 됩니다.
- 항공: 등록되지 않은 상태에서 정보를 알려 주거나 '새로 입력(덮어쓰기)'을 고른 뒤 정보를 알려 주면 mode="replace".
  '새로 입력(덮어쓰기)'을 골랐지만 아직 새 정보를 말하지 않았으면 form="flight"로 양식을 보여주세요.
  '기존 정보 수정'을 고르면 mode="update"로, 무엇을 바꿀지 아직 말하지 않았으면 reply로 바꿀 내용을 물어보세요.
- 숙소: 처음 등록하거나 '새로운 숙소 추가'를 고른 뒤 숙소를 알려 주면 mode="add"(기존 숙소는 그대로 둡니다).
  '새로운 숙소 추가'를 골랐지만 아직 숙소를 말하지 않았으면 form="hotel"로 양식을 보여주세요.
  '기본 정보 수정'을 고르면 mode="update"로 hotel_id(새로 제안한 숙소는 이름)로 가리킨 숙소의 말한 항목만 채우세요.
- 사용자가 말한 정보만 옮겨 적고, 말하지 않은 항목은 null로 두세요(지어내거나 기존 값을 다시 적지 마세요).
  - 공항은 IATA 코드와 한국어 이름을 함께 적으세요.
  - 출발 시간은 받지 않습니다. '9시 비행기'처럼 출발 시간을 말해도 적지 말고, 도착 시간만 arrival_time에 적으세요.
  - 날짜를 말하지 않으면 date는 null로 두세요(가는 날은 여행 첫날, 오는 날은 마지막 날로 등록됩니다).
  - 숙소 이름이 있으면 search_query(숙소 이름 + 도시)를 적으세요.
- 등록·수정할 때 reply는 정리한 내용을 짧게 확인하고, 비어 있는 항목은 나중에 알려 주면 채울 수 있다고 안내하세요."""


class PlannerError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def flight_summary(flight):
    """등록된 항공 정보를 한 줄로 (없으면 '미등록')"""
    if not flight:
        return "미등록"

    def leg(prefix, label, at_key):
        dep = (flight.get(f"{prefix}departure_airport") or {}).get("name") or "?"
        arr = (flight.get(f"{prefix}arrival_airport") or {}).get("name") or "?"
        parts = [f"{dep} → {arr}", flight.get(f"{prefix}airline") or "", flight.get(f"{prefix}flight_number") or ""]
        when = flight.get(at_key) or ""
        return f"{label} " + " ".join(part for part in parts if part) + (f" ({when})" if when else "")

    return leg("", "가는 편", "departure_at") + " / " + leg("return_", "오는 편", "return_arrival_at")


def trip_context(trip, days, items_by_day, draft=None):
    """
    현재 여행·일정을 모델에 줄 텍스트로 정리한다.
    draft: 같은 대화에서 아직 적용하지 않은 항공·숙소 제안 (있으면 등록 정보 대신 보여준다)
    """
    draft = draft or {}
    lines = [
        f"여행지: {trip.destination_label}",
        f"기간: {trip.start_date} ~ {trip.end_date} ({trip.nights}박 {trip.nights + 1}일)",
    ]
    pending = " (이번 대화에서 제안한 내용 포함, 아직 적용 전)"
    flight = draft.get("flight_info")
    lines.append(f"항공 등록 정보{pending if flight else ''}: " + flight_summary(flight or trip.flight_info))
    if draft.get("hotels") is not None:
        hotels = [
            (f"[hotel_id={h['id']}] " if h.get("id") else "[새 숙소] ") + f"{h['name']} ({h['check_in']}~{h.get('check_out') or '?'})"
            for h in draft["hotels"]
        ]
        lines.append(f"숙소 등록 정보{pending}: " + (", ".join(hotels) or "미등록"))
    else:
        hotels = [f"[hotel_id={h.id}] {h.name} ({h.check_in}~{h.check_out or '?'})" for h in trip.hotels.all()]
        lines.append("숙소 등록 정보: " + (", ".join(hotels) or "미등록"))
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


def propose(trip, days, items_by_day, conversation, draft=None):
    """
    conversation: [{"role": "user"|"assistant", "content": str}, ...] (마지막은 사용자 메시지)
    가장 최근 사용자 메시지 앞에 현재 여행 정보를 붙여 보낸다(적용 후 바뀐 일정을 반영하려고).
    draft: 같은 대화에서 아직 적용하지 않은 항공·숙소 제안
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise PlannerError("AI 키(ANTHROPIC_API_KEY)가 설정되지 않았어요.", status_code=503)

    messages = [{"role": turn["role"], "content": turn["content"]} for turn in conversation]
    context = trip_context(trip, days, items_by_day, draft)
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
