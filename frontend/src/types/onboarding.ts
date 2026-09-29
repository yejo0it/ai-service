/**
 * 온보딩(여행 만들기) 화면 상태 타입.
 * Step 1~3 입력값을 OnboardingData 하나에 누적했다가 buildTripPayload로 TripPayload를 만든다.
 */

import type { Destination } from "./api";

/** Step 1의 여행지 한 줄. id는 행 삭제 시 React key가 밀리지 않게 하는 값(전송하지 않음). */
export interface DestinationDraft extends Destination {
  id: string;
}

/**
 * Step 3의 숙소 한 칸. id·sessionToken·city는 화면 전용이고 전송하지 않는다.
 * 날짜는 "YYYY-MM-DD", 아직 고르지 않았으면 빈 문자열.
 */
export interface HotelDraft {
  id: string;
  /** Google Places 자동완성 세션 UUID. 숙소를 고르면(세션 종료) 새 토큰으로 바꾼다. */
  sessionToken: string;
  /** 검색 범위로 쓰는 여행지(Step 1의 도시명) */
  city: string;
  name: string;
  place_id: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  city_code: string;
  check_in: string;
  check_out: string;
}

/** "flight": 항공권 등록, "dates": 날짜만 등록 */
export type DateMode = "flight" | "dates";

export interface OnboardingData {
  // Step 1
  destinations: DestinationDraft[];
  // Step 2
  dateMode: DateMode;
  airline: string;
  /** 선택한 항공사의 IATA 코드. 편명 앞에 붙는다. */
  airlineCode: string;
  flightNumber: string;
  /** "YYYY-MM-DDTHH:mm" */
  departureAt: string;
  /** 귀국 항공사 동일 */
  sameReturnAirline: boolean;
  returnAirline: string;
  returnAirlineCode: string;
  returnFlightNumber: string;
  /** "YYYY-MM-DDTHH:mm" */
  returnArrivalAt: string;
  startDate: string;
  endDate: string;
  // Step 3
  skipHotel: boolean;
  hotels: HotelDraft[];
}

export type OnboardingPatch = Partial<OnboardingData>;

export interface HotelErrors {
  name?: string;
  stay?: string;
}

/** 단계별 검증 에러. 키는 OnboardingData 필드명, 숙소는 hotel.id별로 모은다. */
export interface OnboardingErrors {
  destinations?: string;
  airline?: string;
  flightNumber?: string;
  returnAirline?: string;
  departureAt?: string;
  returnArrivalAt?: string;
  startDate?: string;
  endDate?: string;
  hotels?: Record<string, HotelErrors>;
}

/** 여행 기간 ("YYYY-MM-DD", 아직 정하지 않았으면 빈 문자열). 숙박 기간 선택 범위를 제한한다. */
export interface TripRange {
  start: string;
  end: string;
}

/** 다른 숙소와 겹치는지 볼 때 쓰는 숙박 기간 */
export type Stay = Pick<HotelDraft, "id" | "check_in" | "check_out">;

/** 항공사 이름 + IATA 코드 한 쌍 */
export interface AirlineSelection {
  name: string;
  code: string;
}

export interface OnboardingContextValue {
  data: OnboardingData;
  update: (patch: OnboardingPatch) => void;
  errors: OnboardingErrors;
  step: number;
  tripRange: TripRange;
  /** 여행지 변경으로 숙소가 정리됐을 때의 안내 문구 */
  hotelNotice: string;
  dismissHotelNotice: () => void;
}
