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
  city_code: string;
}

export type DateSource = "flight" | "manual";

export interface FlightInfo {
  airline?: string;
  /** IATA 코드 + 번호 (예: "KE001") */
  flight_number: string;
  departure_at: ISODateTime;
  arrival_at?: ISODateTime | null;
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

export interface Trip extends Omit<TripPayload, "hotels"> {
  id: number;
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
