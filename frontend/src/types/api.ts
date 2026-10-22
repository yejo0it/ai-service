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
  /** 내가 만든 여행인지 (초대받은 일행이면 false: 여행 삭제·초대 링크 발급은 만든 회원만 한다) */
  is_owner: boolean;
  hotels: Hotel[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/* ------------------------------------------------------------------ *
 * 일행 초대
 * ------------------------------------------------------------------ */

/** 초대 링크(/trips/invite/{token}). 여행마다 하나, 7일 동안 쓸 수 있다. */
export interface TripInvitation {
  token: string;
  expires_at: ISODateTime;
}

export interface TripMemberUser {
  id: number;
  /** 이름만 보여준다 (이메일은 다른 회원에게 보내지 않는다) */
  name: string;
}

export interface TripMembers {
  is_owner: boolean;
  /** 여행을 만든 회원 */
  owner: TripMemberUser | null;
  /** 초대받아 함께하는 일행 (만든 회원 제외) */
  members: (TripMemberUser & { joined_at: ISODateTime })[];
  /** 만든 회원을 뺀 최대 일행 수 */
  max_members: number;
  /** 지금 쓸 수 있는 초대 링크. 없거나 만료됐으면 null */
  invitation: TripInvitation | null;
}

export interface InvitationAcceptResponse {
  trip_id: number;
  /** 이번에 새로 일행이 됐는지 (이미 함께하는 여행이면 false) */
  joined: boolean;
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
  /** 소셜 가입 회원은 비어 있을 수 있다. */
  email: string;
  /** 닉네임 (가입할 때 비우면 서버가 만든 랜덤 닉네임) */
  name: string;
  /** 휴대폰 인증을 마친 번호만 저장되므로 값이 있으면 인증된 번호다. 없으면 빈 문자열 */
  phone: string;
  /** 프로필 사진 경로(`/media/...`). 화면에서는 mediaUrl로 바꿔 쓴다. */
  avatar: string | null;
  /** 이메일 가입 회원인지 (소셜 가입 회원은 비밀번호가 없어 이메일을 바꿀 수 없다) */
  has_password: boolean;
  /** 비밀번호를 마지막으로 바꾼 날짜(YYYY-MM-DD). 바꾼 적이 없으면 가입일, 소셜 가입 회원은 null */
  password_updated_at: string | null;
  /** 연결된 소셜 계정 */
  social_providers: SocialProvider[];
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
  /** 선택. 비우면 서버가 랜덤 닉네임을 만든다. */
  name?: string;
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
  /** unit 만큼의 원화 금액 (표시용, 소수 2자리 반올림) */
  krw: number;
  /** 1원당 현지 통화 금액(반올림 없음). 환율 계산기가 쓴다. 없으면 krw로 계산한다. */
  per_krw?: number;
  /** 이 통화를 쓰는 여행 도시 이름 (예: ["도쿄", "오사카"]). 환율 계산기에서 여행지를 고를 때 쓴다. */
  cities?: string[];
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
  /** AI가 정한 예상 체류 시간(분). 없으면 null */
  stay_minutes?: number | null;
  /** 이동 시간으로 계산한 예상 도착 시각(HH:MM, 추정치). 순서·시간을 바꾸면 사라진다 */
  expected_arrival?: string | null;
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

export type PackingCategory = "todo" | "essentials" | "toiletries" | "clothing" | "electronics" | "medicine" | "etc";

/** 여행 체크리스트 항목(준비물·해야 할 일). is_default는 처음 넣어 준 기본 준비물 */
export interface PackingItem {
  id: number;
  category: PackingCategory;
  text: string;
  done: boolean;
  is_default: boolean;
}

/* ------------------------------------------------------------------ *
 * 여행 경비
 * ------------------------------------------------------------------ */

export type ExpenseCategory = "transport" | "lodging" | "food" | "sightseeing" | "shopping" | "etc";

/** 지출 한 건. 금액은 원 단위 정수(문자열로 오는 amount는 입력 통화 기준)다. */
export interface Expense {
  id: number;
  title: string;
  /** 입력한 금액 (서버가 Decimal 문자열로 보낸다) */
  amount: string;
  currency: string;
  /** 원화 환산 금액 */
  amount_krw: number;
  /** 지출 당시 적용한 환율(1원당 현지 통화 금액). 원화 지출은 null */
  rate_per_krw: string | null;
  spent_on: ISODate;
  category: ExpenseCategory;
  memo: string;
  /** 결제자 회원 번호. 탈퇴한 결제자도 같은 번호로 남는다. */
  payer_id: number | null;
  payer_name: string;
  /** 비용을 나누는 인원과 각자의 부담액(균등 분할, 나머지는 1원씩). 분담 인원을 정하지 않은 지출은 빈 배열 */
  participants: ExpenseParticipant[];
  /** 분담 방식: 균등 분할 또는 사람마다 금액을 직접 입력 */
  split_method: SplitMethod;
}

export type SplitMethod = "equal" | "custom";

export interface ExpenseParticipant {
  id: number;
  name: string;
  share_krw: number;
  /** 직접 입력일 때 입력한 금액(지출 통화 기준, Decimal 문자열). 균등 분할이면 null */
  amount: string | null;
}

/** 지출 목록과 예산 요약. 합계는 서버가 정수 원으로 계산한다. */
export interface ExpensesResponse {
  /** 총예산. 설정하지 않았으면 null */
  budget_krw: number | null;
  total_krw: number;
  /** 남은 예산(초과하면 음수). 예산이 없으면 null */
  remaining_krw: number | null;
  by_category: Record<ExpenseCategory, number>;
  expenses: Expense[];
}

export interface ExpensePayload {
  title: string;
  /** 입력 통화 기준 금액(문자열로 보내 소수 오차를 피한다) */
  amount: string;
  currency: string;
  spent_on: ISODate;
  category: ExpenseCategory;
  memo: string;
  /** 결제자 회원 번호. 보내지 않으면 등록한 사람(수정할 때는 그대로) */
  payer_id?: number;
  /** 비용을 나눌 회원 번호. 보내지 않으면 그대로(새 지출은 나누지 않는 지출) */
  participant_ids?: number[];
  /** 분담 방식. 직접 입력이면 participant_amounts로 사람마다 금액을 보낸다(합계는 지출 금액과 같아야 한다). */
  split_method?: SplitMethod;
  participant_amounts?: { id: number; amount: string }[];
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
  /** 미리보기에서 실제 이동 시간으로 정한 날짜별 방문 순서. 적용할 때 그대로 돌려보낸다(서버가 저장). */
  order?: Record<string, string[]>;
  /** 순서를 정한 날짜별 예상 도착 시각({날짜: {카드 키: "HH:MM"}}). 적용할 때 그대로 돌려보내면 서버가 저장한다. */
  etas?: Record<string, Record<string, string>>;
}

/** 같은 대화에서 아직 적용하지 않은 항공·숙소 제안 */
export interface AiRegistrationDraft {
  flight_info: FlightInfo | null;
  hotels: AiHotelProposal[] | null;
}

/** 두 장소 사이 이동 (Google 길찾기 결과). 정보를 찾지 못한 구간은 null이며, 시간을 추정해 채우지 않는다. */
export interface AiRouteLeg {
  mode: "walk" | "transit";
  minutes: number;
  meters: number;
  /** 대중교통 환승 횟수 (0이면 환승 없음) */
  transfers?: number;
}

export interface AiPreviewDay {
  day: ISODate;
  items: {
    id: number | null;
    title: string;
    kind: ItineraryKind;
    time: string;
    time_label: string;
    status: "new" | "moved" | "same";
    /** 예상 도착 시각(HH:MM). 실제 이동 시간으로 계산한 날의 새·이동 장소만 */
    eta?: string;
  }[];
  /** items[i] -> items[i + 1] 이동. 실제 이동 시간으로 순서를 정하지 않은 날은 모두 null */
  legs?: (AiRouteLeg | null)[];
  /** 이 날의 순서를 정한 근거: google(실제 이동 시간) · partial(일부 구간만) · straight_line(직선거리) */
  route_basis?: "google" | "partial" | "straight_line" | null;
  /** 영업시간·시간 충돌 경고 */
  warnings?: string[];
}

/** AI 답변의 근거 문서 */
export interface AiSource {
  id: number;
  /** 문서 제목 (예: Japan) */
  title: string;
  /** 섹션 경로 (예: Get in > By plane) */
  section: string;
  url: string;
  license: string;
}

export interface AiProposeResponse {
  reply: string;
  /** 적용할 때 그대로 돌려보낸다 */
  proposal: AiProposal;
  preview: AiPreviewDay[];
  removed: { id: number; title: string }[];
  /** 실제 장소를 찾지 못한 이름 */
  unresolved: string[];
  /** 방문 순서를 정한 근거. none이면 새로 넣거나 옮긴 장소가 없어 해당 없음 */
  route?: { basis: "google" | "partial" | "straight_line" | "none"; note: string };
  /** 서비스 범위 밖 요청이라 거절했는지 (변경 제안 없음) */
  refused?: boolean;
  /** 가리고 AI에 보낸 민감정보 종류 (예: 카드번호, 비밀번호) */
  redacted?: string[];
  /** 답변 아래에 보여줄 선택 버튼 (예: 기존 정보 수정 / 새로 입력) */
  choices: string[];
  /** 답변 근거로 쓴 여행 정보 문서 (Wikivoyage 발췌) */
  sources?: AiSource[];
  /** 항공·숙소 등록 미리보기 */
  registration: {
    flight: FlightInfo | null;
    hotels: AiHotelProposal[] | null;
    removed_hotels: { id: number; title: string }[];
  };
}

/** 일정 카드 사이 이동 구간의 한 단계 (Google Routes·NAVITIME 결과) */
export type LegStep =
  | { type: "walk"; minutes: number; meters: number; start_time: string; description: string }
  | { type: "drive"; minutes: number; meters: number; start_time: string; description: string }
  | {
      type: "transit";
      minutes: number;
      start_time: string;
      line_name: string;
      line_color: string;
      from_stop: string;
      to_stop: string;
      /** 통과 정거장 수. 모르면 0 */
      stop_count: number;
      /** 아래는 NAVITIME(일본) 구간에만 있다. 한국어 이름과 원어를 함께 준다(한국어를 확보하지 못하면 둘 다 원어). */
      line_name_ja?: string;
      /** 열차 종별(예: "쾌속", "신쾌속", "특급"). 보통(각역 정차)이거나 모르면 빈 문자열 */
      train_type?: string;
      train_type_ja?: string;
      operator?: string;
      operator_ja?: string;
      from_stop_ja?: string;
      to_stop_ja?: string;
      /** 역 번호 (예: "JY20") */
      from_number?: string;
      to_number?: string;
      /** 행선지 (예: "시나가와행") */
      direction?: string;
      direction_ja?: string;
      /** 이 탑승을 마친 뒤 다음 열차로 갈아타는 데 걸리는 시간(분) */
      transfer_minutes?: number | null;
    };

/** 직전 일정 -> 이 일정 이동 구간. 정보가 없는 구간은 status가 not_found이고 단계가 비어 있다(시간을 추정하지 않는다). */
export interface ItineraryLeg {
  from_item_id: number;
  to_item_id: number;
  status: "ok" | "not_found";
  mode: "transit" | "walk" | "drive";
  total_minutes: number;
  /** 요금 표기 (예: "¥253"). 모르면 null */
  fare_label: string | null;
  steps: LegStep[];
}

/** 지출에 쓸 수 있는 통화 한 개와 지금 환율 */
export interface ExpenseCurrency {
  currency: string;
  name: string;
  flag: string;
  /** 소수 자릿수(엔·동은 0, 그 밖은 2) */
  decimals: number;
  /** 1원당 현지 통화 금액(Decimal 문자열) */
  per_krw: string;
}

export interface ExpenseCurrencies {
  /** 이 여행 도시들의 통화(원화 제외) */
  trip_currencies: string[];
  currencies: ExpenseCurrency[];
  updated_at: string;
}

/** 사용자별 정산: 결제한 금액 · 부담액 · 순액(받을 돈은 +, 보낼 돈은 −) */
export interface SettlementBalance {
  id: number;
  name: string;
  paid_krw: number;
  share_krw: number;
  net_krw: number;
  /** 지금 여행에 함께하는 사람인지(나간 일행·탈퇴한 회원은 false) */
  active: boolean;
}

/** 누가 누구에게 얼마를 보내면 정산이 끝나는지 */
export interface SettlementTransfer {
  from_id: number;
  from_name: string;
  to_id: number;
  to_name: string;
  amount_krw: number;
}

export interface Settlement {
  balances: SettlementBalance[];
  transfers: SettlementTransfer[];
  /** 정산에 들어간 지출 합계(분담 인원을 정한 지출) */
  settled_krw: number;
  /** 분담 인원을 정하지 않아 정산에서 빠진 지출 수 */
  excluded_count: number;
}

/* ------------------------------------------------------------------ *
 * 여행 요약 (한 줄 메모 · 사진)
 * ------------------------------------------------------------------ */

/** 여행 요약 사진. url은 API 주소 기준 경로이며 로그인한 여행 참여자만 받을 수 있다(공개 주소 없음). */
export interface TripPhoto {
  id: number;
  order: number;
  width: number;
  height: number;
  size_bytes: number;
  url: string;
}

export interface TripSummary {
  memo: string;
  photos: TripPhoto[];
  max_photos: number;
  /** 여행 시작일부터 쓸 수 있다 */
  writable: boolean;
}
