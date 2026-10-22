"""
예약 정보 스키마. AI 응답(구조화된 출력)과 사용자가 고친 값을 같은 모양으로 다룬다.

- 문서에서 확인할 수 없는 값은 null이다(추측하지 않는다).
- 예약번호·승객 이름·연락처 같은 개인정보 필드는 두지 않는다(추출하지 않는다).
- 날짜는 'YYYY-MM-DD', 시각은 'HH:MM'(24시간, 해당 공항·숙소의 현지 시각)이다.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class FlightSegment(BaseModel):
    """비행 구간 하나(경유·다구간은 구간마다 하나씩)."""

    airline_name: Optional[str] = Field(description="항공사 이름. 문서에 적힌 그대로 (예: 대한항공, Korean Air, ANA)")
    flight_number: Optional[str] = Field(description="항공편명. 항공사 코드 + 숫자 (예: KE703). 문서에 없으면 null")
    departure_airport_code: Optional[str] = Field(description="출발 공항 IATA 3글자 코드. 문서에 코드가 적혀 있을 때만, 아니면 null")
    departure_airport_name: Optional[str] = Field(description="출발 공항 이름. 문서에 적힌 그대로")
    arrival_airport_code: Optional[str] = Field(description="도착 공항 IATA 3글자 코드. 문서에 코드가 적혀 있을 때만, 아니면 null")
    arrival_airport_name: Optional[str] = Field(description="도착 공항 이름. 문서에 적힌 그대로")
    departure_date: Optional[str] = Field(description="출발 날짜 'YYYY-MM-DD' (출발 공항 현지). 연도를 알 수 없으면 null")
    departure_time: Optional[str] = Field(description="출발 시각 'HH:MM' 24시간 (출발 공항 현지). 문서에 없으면 null")
    arrival_date: Optional[str] = Field(description="도착 날짜 'YYYY-MM-DD' (도착 공항 현지, 야간 비행은 출발 날짜와 다를 수 있음)")
    arrival_time: Optional[str] = Field(description="도착 시각 'HH:MM' 24시간 (도착 공항 현지). 문서에 없으면 null")
    direction: Optional[Literal["outbound", "return"]] = Field(
        description="왕복 항공권에서 가는 편은 outbound, 오는 편은 return. 문서에서 확인되지 않으면 null"
    )
    notes: list[str] = Field(description="이 구간에서 읽기 어렵거나 불확실했던 점을 한국어로 짧게(없으면 빈 목록)")


class FlightItinerary(BaseModel):
    """항공권 예약 한 건. 왕복·경유·다구간이면 구간이 여러 개다."""

    status: Optional[str] = Field(description="예약 상태가 문서에 적혀 있을 때만 (예: 확정, Confirmed, OK). 없으면 null")
    segments: list[FlightSegment]


class FlightDocument(BaseModel):
    itineraries: list[FlightItinerary]


class HotelStay(BaseModel):
    """숙소 예약 한 건."""

    name: Optional[str] = Field(description="숙소 이름. 문서에 적힌 그대로")
    address: Optional[str] = Field(description="숙소 주소. 문서에 적혀 있을 때만, 아니면 null")
    check_in_date: Optional[str] = Field(description="체크인 날짜 'YYYY-MM-DD'. 연도를 알 수 없으면 null")
    check_out_date: Optional[str] = Field(description="체크아웃 날짜 'YYYY-MM-DD'. 연도를 알 수 없으면 null")
    check_in_time: Optional[str] = Field(description="체크인 시각 'HH:MM' 24시간. 문서에 명시된 경우만, 아니면 null")
    check_out_time: Optional[str] = Field(description="체크아웃 시각 'HH:MM' 24시간. 문서에 명시된 경우만, 아니면 null")
    status: Optional[str] = Field(description="예약 상태가 문서에 적혀 있을 때만. 없으면 null")
    notes: list[str] = Field(description="읽기 어렵거나 불확실했던 점을 한국어로 짧게(없으면 빈 목록)")


class HotelDocument(BaseModel):
    stays: list[HotelStay]


FLIGHT, HOTEL = "flight", "hotel"
KINDS = (FLIGHT, HOTEL)
DOCUMENT_MODELS = {FLIGHT: FlightDocument, HOTEL: HotelDocument}

# 필드 목록(정규화·검증이 같은 순서를 쓴다)
SEGMENT_TEXT_FIELDS = ("airline_name", "departure_airport_name", "arrival_airport_name")
STAY_TEXT_FIELDS = ("name", "address")
