/**
 * 백엔드(Django REST Framework) 요청·응답 타입.
 * 필드명은 API 그대로(snake_case)이며, 날짜는 "YYYY-MM-DD", 일시는 ISO 8601 문자열이다.
 */

/* ------------------------------------------------------------------ *
 * 공통
 * ------------------------------------------------------------------ */

/** "YYYY-MM-DD" */
export type ISODate = string;
/** "YYYY-MM-DDTHH:mm" 또는 ISO 8601 일시 */
export type ISODateTime = string;

/**
 * DRF 에러 응답 본문.
 * 필드 에러는 { field: ["메시지"] }, 그 밖의 에러는 { detail: "메시지" } 형태다.
 */
export type ApiErrorData = string | { detail?: string; [field: string]: unknown };

/* ------------------------------------------------------------------ *
 * 여행 (trips)
 * ------------------------------------------------------------------ */

/** 여행지 한 곳. city_code는 IATA 도시 코드(예: TYO)이며 없으면 빈 문자열. */
export interface Destination {
  city: string;
  /** 서비스 자체 도시 id (예: "tokyo"). 화면에는 보여주지 않는다. */
  city_code: string;
}

export type DateSource = "flight" | "manual";

/** 목록에서 고른 공항 */
export interface Airport {
  /** IATA 공항 코드 (예: ICN) */
  code: string;
  /** 표시 이름 (예: 인천공항 1터미널) */
  name: string;
}

export interface FlightInfo {
  airline?: string;
  /** IATA 코드 + 번호 (예: "KE001") */
  flight_number: string;
  departure_at: ISODateTime;
  arrival_at?: ISODateTime | null;
  departure_airport?: Airport | null;
  arrival_airport?: Airport | null;
  return_departure_airport?: Airport | null;
  return_arrival_airport?: Airport | null;
  return_airline?: string;
  return_flight_number?: string;
  return_departure_at?: ISODateTime | null;
  return_arrival_at?: ISODateTime | null;
  note?: string;
}

/** 숙소 저장 요청. Google Places에서 고른 숙소는 place_id·좌표가 채워진다. */
export interface HotelPayload {
  name: string;
  address: string;
  place_id: string;
  latitude: number | null;
  longitude: number | null;
  /** Google Places 전화번호 (없으면 빈 문자열) */
  phone: string;
  city_code: string;
  check_in: ISODate;
  /** 체크아웃 미정이면 null */
  check_out: ISODate | null;
}

export interface Hotel extends HotelPayload {
  id: number;
  nights: number | null;
}

export interface TripPayload {
  destinations: Destination[];
  start_date: ISODate;
  end_date: ISODate;
  date_source: DateSource;
  flight_info: FlightInfo | null;
  hotels: HotelPayload[];
}

/** 여행 색상 (기본 색상 + 서비스 대표색 인디고) */
export type TripColorKey = "indigo" | "red" | "orange" | "yellow" | "green" | "blue" | "purple" | "gray";

export interface Trip extends Omit<TripPayload, "hotels"> {
  id: number;
  /** 사용자가 고른 캘린더 색. 비어 있으면 자동 색상 */
  color: TripColorKey | "";
  /** "도쿄 → 오사카" 형태의 동선 표기 */
  destination_label: string;
  has_flight: boolean;
  nights: number;
  hotels: Hotel[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Airline {
  id: number;
  name_ko: string;
  iata_code: string;
  country: string | null;
}

/* ------------------------------------------------------------------ *
 * 숙소 검색 (Google Places)
 * ------------------------------------------------------------------ */

export interface HotelSearchParams {
  input: string;
  /** 숙소 입력 세션마다 만드는 UUID. 같은 토큰으로 상세 조회하면 자동완성이 과금되지 않는다. */
  sessionToken: string;
  city?: string;
  cityCode?: string;
}

export interface HotelSuggestion {
  place_id: string;
  name: string;
  description: string;
}

export interface HotelDetail {
  place_id: string;
  address: string;
  latitude: number | null;
  longitude: number | null;
  phone: string;
}

/* ------------------------------------------------------------------ *
 * 회원 (accounts)
 * ------------------------------------------------------------------ */

export interface AuthUser {
  id: number;
  email: string;
  name: string;
}

/** 로그인·가입·소셜 로그인 응답. 프론트는 이 값을 그대로 세션으로 저장한다. */
export interface AuthSession {
  token: string;
  user: AuthUser;
}

export interface LoginPayload {
  email: string;
  password: string;
}

/** 휴대폰 인증을 마쳤다는 증명. phone/verify 응답의 토큰을 함께 보낸다. */
export interface VerifiedPhonePayload {
  phone: string;
  phone_verification_token: string;
}

export interface NewPasswordPayload {
  password: string;
  password_confirm: string;
}

export interface SignupPayload extends VerifiedPhonePayload, NewPasswordPayload {
  email: string;
}

export interface CheckEmailResponse {
  available: boolean;
}

export interface PhoneCodeResponse {
  /** 인증번호 유효 시간(초) */
  expires_in: number;
  /** SMS 미연동 개발 서버(DEBUG)에서만 내려오는 인증번호 */
  debug_code?: string;
}

export interface PhoneVerifyResponse {
  verification_token: string;
}

export type FindIdPayload = VerifiedPhonePayload;

export interface FindIdResponse {
  emails: string[];
}

export interface PasswordResetVerifyPayload extends VerifiedPhonePayload {
  email: string;
}

export interface PasswordResetVerifyResponse {
  /** 15분 동안 유효한 1회용 재설정 토큰 */
  reset_token: string;
}

export interface PasswordResetConfirmPayload extends NewPasswordPayload {
  reset_token: string;
}

export type SocialProvider = "kakao" | "naver";

/** 카카오는 redirect_uri, 네이버는 state를 인가 코드와 함께 보낸다. */
export type SocialLoginPayload =
  | { code: string; redirect_uri: string }
  | { code: string; state: string };

/* ------------------------------------------------------------------ *
 * 홈 위젯: 여행지 날씨 · 환율 (travel-info)
 * ------------------------------------------------------------------ */

/** weather_code는 WMO 날씨 코드 (0 맑음, 61 비 등) */
export interface DailyWeather {
  date: ISODate;
  weather_code: number | null;
  max: number | null;
  min: number | null;
}

export interface CityWeather {
  city_code: string;
  current: { temperature: number | null; weather_code: number | null };
  /** 오늘부터 최대 16일 */
  daily: DailyWeather[];
}

export interface ExchangeRate {
  currency: string;
  /** 한글 통화 이름 (엔, 유로 등) */
  name: string;
  flag: string;
  /** 표시 단위 (엔·동 등은 100) */
  unit: number;
  /** unit 만큼의 원화 금액 */
  krw: number;
}

export interface ExchangeRatesResponse {
  rates: ExchangeRate[];
  /** 환율 기준 시각 (UTC 문자열) */
  updated_at: string;
}

/* ------------------------------------------------------------------ *
 * 여행 상세 일정 (itinerary) · 체크리스트 · 짐싸기 노트 · AI
 * ------------------------------------------------------------------ */

export type ItineraryKind = "flight" | "hotel" | "airport" | "sight" | "restaurant" | "cafe";
/** 직접 추가할 수 있는 장소 유형 */
export type PlaceKind = Exclude<ItineraryKind, "flight">;

/** 카드 안의 위치 (지도 핀). kind는 핀 색 */
export interface ItineraryStop {
  kind: "airport" | "hotel" | "place" | "city";
  caption: string;
  label: string;
  lat?: number | null;
  lng?: number | null;
}

export interface ChecklistItem {
  id: number;
  text: string;
  done: boolean;
  /** 짐싸기 노트 '일정 연동 항목'에 표시 */
  in_packing_note: boolean;
}

export interface ItineraryItem {
  id: number;
  day: ISODate;
  order: number;
  kind: ItineraryKind;
  source: "auto" | "manual" | "ai";
  title: string;
  /** "HH:MM" 또는 null */
  time: string | null;
  /** 체크인·숙박·체크아웃·출국·귀국 */
  time_label: string;
  subtitle: string;
  stops: ItineraryStop[];
  place_id: string;
  address: string;
  phone: string;
  /** 요일별 영업시간 문장 */
  opening_hours: string[];
  memo: string;
  checklist: ChecklistItem[];
}

export interface ItineraryResponse {
  initialized: boolean;
  items: ItineraryItem[];
}

/** 처음 열 때 저장하는 항공편·숙소 카드 */
export interface ItineraryCardInput {
  day: ISODate;
  kind: ItineraryKind;
  title: string;
  time: string;
  time_label: string;
  subtitle: string;
  stops: ItineraryStop[];
  phone?: string;
}

/** 공항(항공편) 직접 추가: 단일 노선 한 편 */
export interface AddFlightPayload {
  kind: "flight";
  day: ISODate;
  time: string;
  airline: string;
  flight_number: string;
  departure_airport: { code: string; name: string; lat: number; lng: number };
  arrival_airport: { code: string; name: string; lat: number; lng: number };
}

/** 숙소 직접 추가: 숙박 기간과 함께 여행 숙소로 등록 */
export interface AddHotelStayPayload {
  kind: "hotel";
  place_id: string;
  session_token: string;
  city_code: string;
  check_in: ISODate;
  check_out: ISODate;
}

export interface AddPlacePayload {
  kind: PlaceKind;
  day: ISODate;
  time: string;
  place_id: string;
  session_token: string;
}

export interface PackingLinkedItem extends ChecklistItem {
  item_id: number;
  item_title: string;
  day: ISODate;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

/** AI로 등록·수정할 숙소 (새 숙소는 id가 null) */
export interface AiHotelProposal {
  id: number | null;
  name: string;
  address: string;
  place_id: string;
  latitude: number | null;
  longitude: number | null;
  phone: string;
  city_code: string;
  check_in: ISODate;
  check_out: ISODate | null;
  nights: number | null;
  status: "new" | "updated" | "same";
}

export interface AiProposal {
  additions: unknown[];
  remove_item_ids: number[];
  moves: unknown[];
  /** 항공 등록 정보를 바꾸는지 (flight_info가 그 값) */
  flight_changed: boolean;
  flight_info: FlightInfo | null;
  /** 바뀐 뒤의 숙소 전체 목록 (null이면 숙소는 그대로) */
  hotels: AiHotelProposal[] | null;
  /** 바뀐 항공·숙소로 다시 만든 경로의 자동 항공·숙소 카드 (적용할 때 프론트가 채운다) */
  auto_cards?: ItineraryCardInput[];
}

/** 같은 대화에서 아직 적용하지 않은 항공·숙소 제안 */
export interface AiRegistrationDraft {
  flight_info: FlightInfo | null;
  hotels: AiHotelProposal[] | null;
}

export interface AiPreviewDay {
  day: ISODate;
  items: { id: number | null; title: string; kind: ItineraryKind; time: string; time_label: string; status: "new" | "moved" | "same" }[];
}

export interface AiProposeResponse {
  reply: string;
  /** 적용할 때 그대로 돌려보낸다 */
  proposal: AiProposal;
  preview: AiPreviewDay[];
  removed: { id: number; title: string }[];
  /** 실제 장소를 찾지 못한 이름 */
  unresolved: string[];
  /** 서비스 범위 밖 요청이라 거절했는지 (변경 제안 없음) */
  refused?: boolean;
  /** 답변 아래에 보여줄 선택 버튼 (예: 기존 정보 수정 / 새로 입력) */
  choices: string[];
  /** 항공·숙소 등록 미리보기 */
  registration: {
    flight: FlightInfo | null;
    hotels: AiHotelProposal[] | null;
    removed_hotels: { id: number; title: string }[];
  };
}
