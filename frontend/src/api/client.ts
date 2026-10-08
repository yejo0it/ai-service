import axios, { isAxiosError } from "axios";
import { clearSession, getSession } from "../auth/session";
import type {
  AddFlightPayload,
  AddHotelStayPayload,
  AddPlacePayload,
  AiProposal,
  AiProposeResponse,
  AiRegistrationDraft,
  Airline,
  ChatTurn,
  ChecklistItem,
  ItineraryCardInput,
  ItineraryItem,
  ItineraryResponse,
  PackingLinkedItem,
  PlaceKind,
  ApiErrorData,
  AuthSession,
  AuthUser,
  CheckEmailResponse,
  CityWeather,
  ExchangeRatesResponse,
  FindIdPayload,
  FindIdResponse,
  Hotel,
  HotelDetail,
  HotelPayload,
  HotelSearchParams,
  HotelSuggestion,
  LoginPayload,
  PasswordResetConfirmPayload,
  PasswordResetVerifyPayload,
  PasswordResetVerifyResponse,
  PhoneCodeResponse,
  PhoneVerifyResponse,
  SignupPayload,
  SocialLoginPayload,
  SocialProvider,
  Trip,
  TripColorKey,
  TripPayload,
} from "../types/api";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8003/api/v1",
  headers: { "Content-Type": "application/json" },
  timeout: 10000,
});

// 로그인한 경우 모든 요청에 API 토큰을 붙인다.
api.interceptors.request.use((config) => {
  const token = getSession()?.token;
  if (token) config.headers.Authorization = `Token ${token}`;
  return config;
});

// 토큰이 만료·삭제되어 401이 오면 저장된 세션을 비운다.
api.interceptors.response.use(undefined, (error: unknown) => {
  if (isAxiosError(error) && error.response?.status === 401 && getSession()) clearSession();
  return Promise.reject(error);
});

/** 항공사 목록 조회 */
export const getAirlines = () => api.get<Airline[]>("/airlines/").then((res) => res.data);

/** 로그인한 회원의 여행 목록 (페이지 없이 전체) */
export const listTrips = () => api.get<Trip[]>("/trips/").then((res) => res.data);

/** 여행 하나 (내 여행만) */
export const getTrip = (tripId: number) => api.get<Trip>(`/trips/${tripId}/`).then((res) => res.data);

/** 여행 삭제 (숙소도 함께 삭제된다) */
export const deleteTrip = (tripId: number) => api.delete<void>(`/trips/${tripId}/`);

/** 여행 캘린더 색 변경. 빈 문자열이면 자동 색상 */
export const updateTripColor = (tripId: number, color: TripColorKey | "") =>
  api.patch<Trip>(`/trips/${tripId}/`, { color }).then((res) => res.data);

/** 온보딩 Step 1~3을 한 번에 저장 (hotels 포함 가능) */
export const createTrip = (payload: TripPayload) =>
  api.post<Trip>("/trips/", payload).then((res) => res.data);

/** 단계별 저장이 필요할 때: Step 3만 따로 저장 */
export const createHotel = (tripId: number, payload: HotelPayload) =>
  api.post<Hotel>(`/trips/${tripId}/hotels/`, payload).then((res) => res.data);

/**
 * 숙소 자동완성 (Google Places). sessionToken은 숙소 입력 세션마다 만든 UUID로,
 * 같은 토큰으로 getHotelDetails를 호출하면 세션이 끝나 자동완성 요청이 과금되지 않는다.
 */
export const searchHotels = ({ input, sessionToken, city, cityCode }: HotelSearchParams) =>
  api
    .get<HotelSuggestion[]>("/places/hotels/", {
      params: { input, session_token: sessionToken, city, city_code: cityCode },
    })
    .then((res) => res.data);

/** 선택한 숙소의 주소·좌표 */
export const getHotelDetails = (placeId: string, sessionToken: string) =>
  api
    .get<HotelDetail>(`/places/hotels/${encodeURIComponent(placeId)}/`, {
      params: { session_token: sessionToken },
    })
    .then((res) => res.data);

/** 여행지 현재 날씨 + 일별 예보 (Open-Meteo, 서버 30분 캐시) */
export const getWeather = (cityCode: string) =>
  api
    .get<CityWeather>("/travel-info/weather/", { params: { city_code: cityCode } })
    .then((res) => res.data);

/** 여행 도시들의 현지 통화 환율 (원화 기준, 하루 1회 갱신) */
export const getExchangeRates = (cityCodes: string[]) =>
  api
    .get<ExchangeRatesResponse>("/travel-info/exchange-rates/", {
      params: { city_codes: cityCodes.join(",") },
    })
    .then((res) => res.data);

/* ------------------------------------------------------------------ *
 * 여행 상세 일정 · 체크리스트 · 짐싸기 노트 · AI
 * ------------------------------------------------------------------ */

export const getItinerary = (tripId: number) =>
  api.get<ItineraryResponse>(`/trips/${tripId}/itinerary/`).then((res) => res.data);

/** 처음 열 때 항공편·숙소 카드를 한 번 저장한다 (이미 저장했으면 그대로 돌려준다) */
export const initItinerary = (tripId: number, items: ItineraryCardInput[]) =>
  api.post<ItineraryResponse>(`/trips/${tripId}/itinerary/init/`, { items }).then((res) => res.data);

/** 장소·항공편 직접 추가 (서버가 거리 기준으로 자리를 정한다) */
/** 숙소를 숙박 기간과 함께 등록하면 요약 카드도 바뀌므로 바뀐 여행(trip)을 함께 돌려준다. */
export const addItineraryPlace = (tripId: number, payload: AddPlacePayload | AddFlightPayload | AddHotelStayPayload) =>
  api.post<ItineraryResponse & { trip?: Trip }>(`/trips/${tripId}/itinerary/`, payload).then((res) => res.data);

export const reorderItinerary = (tripId: number, day: string, ids: number[]) =>
  api.post<ItineraryResponse>(`/trips/${tripId}/itinerary/reorder/`, { day, ids }).then((res) => res.data);

/**
 * 일정 카드 수정. time은 "HH:MM" 또는 null(시간 미정).
 * place_id(+session_token)를 주면 장소를 다시 검색해 고른 것으로 보고 이름·주소·전화·영업시간을 바꾼다.
 */
export const updateItineraryItem = (
  itemId: number,
  payload: { memo?: string; time?: string | null; place_id?: string; session_token?: string },
) =>
  api.patch<ItineraryItem>(`/itinerary-items/${itemId}/`, payload).then((res) => res.data);

/**
 * 일정 카드 삭제. 여행 등록 정보에서 만든 항공·숙소 카드를 지우면 서버가 등록 정보도 맞추고
 * 바뀐 여행과 함께 지운 카드 id들을 돌려준다(그 밖에는 null).
 * 숙소 체크인·체크아웃 카드는 그 숙소의 다른 카드까지 지워진다.
 */
export const deleteItineraryItem = (itemId: number) =>
  api
    .delete<{ trip: Trip; removed_ids: number[] } | "">(`/itinerary-items/${itemId}/`)
    .then((res) => (res.data && typeof res.data === "object" ? res.data : null));

export const addChecklistItem = (itemId: number, text: string) =>
  api.post<ChecklistItem>(`/itinerary-items/${itemId}/checklist/`, { text }).then((res) => res.data);

export const updateChecklistItem = (checkId: number, payload: Partial<Omit<ChecklistItem, "id">>) =>
  api.patch<ChecklistItem>(`/checklist-items/${checkId}/`, payload).then((res) => res.data);

export const deleteChecklistItem = (checkId: number) => api.delete<void>(`/checklist-items/${checkId}/`);

/** 짐싸기 노트 '일정 연동 항목' */
export const getPackingNote = (tripId: number) =>
  api.get<{ linked: PackingLinkedItem[] }>(`/trips/${tripId}/packing-note/`).then((res) => res.data);

/** 일정 장소 자동완성 (유형별) */
export const searchPlaces = (params: { input: string; sessionToken: string; cityCode?: string; kind?: PlaceKind }) =>
  api
    .get<HotelSuggestion[]>("/places/search/", {
      params: { input: params.input, session_token: params.sessionToken, city_code: params.cityCode, kind: params.kind },
    })
    .then((res) => res.data);

/** AI와 함께 만들기: 대화 -> 일정 변경 제안과 미리보기 (AI 응답이라 오래 걸릴 수 있다) */
/** draft: 같은 대화에서 아직 적용하지 않은 항공·숙소 제안 (다음 제안이 그 위에 이어서 고친다) */
export const proposeAiPlan = (tripId: number, messages: ChatTurn[], draft?: AiRegistrationDraft) =>
  api
    .post<AiProposeResponse>(`/trips/${tripId}/ai/propose/`, { messages, draft }, { timeout: 120_000 })
    .then((res) => res.data);

/** 적용 결과: 바뀐 일정 + (항공·숙소가 바뀌었을 수 있으므로) 여행 */
export const applyAiPlan = (tripId: number, proposal: AiProposal) =>
  api
    .post<ItineraryResponse & { trip: Trip }>(`/trips/${tripId}/ai/apply/`, { proposal })
    .then((res) => res.data);

/* ------------------------------------------------------------------ *
 * 회원 (로그인 · 가입)
 * 로그인·가입·소셜 로그인은 모두 { token, user }를 돌려준다.
 * ------------------------------------------------------------------ */

export const login = (payload: LoginPayload) =>
  api.post<AuthSession>("/auth/login/", payload).then((res) => res.data);

export const signup = (payload: SignupPayload) =>
  api.post<AuthSession>("/auth/signup/", payload).then((res) => res.data);

/** 가입 가능한 이메일인지 -> { available } */
export const checkEmail = (email: string) =>
  api.post<CheckEmailResponse>("/auth/check-email/", { email }).then((res) => res.data);

/** 인증번호 발송 -> { expires_in, debug_code? } (debug_code는 개발 서버에서만) */
export const requestPhoneCode = (phone: string) =>
  api.post<PhoneCodeResponse>("/auth/phone/request/", { phone }).then((res) => res.data);

/** 인증번호 확인 -> { verification_token } */
export const verifyPhoneCode = (phone: string, code: string) =>
  api
    .post<PhoneVerifyResponse>("/auth/phone/verify/", { phone, code })
    .then((res) => res.data);

/** 저장된 토큰이 아직 유효한지 확인하고 회원 정보를 받는다 (만료·폐기 시 401) */
export const getMe = () => api.get<AuthUser>("/auth/me/").then((res) => res.data);

/** 서버의 API 토큰 폐기 (useLogout에서 세션 삭제와 함께 쓴다) */
export const logout = () => api.post<void>("/auth/logout/");

/** 휴대폰 인증 후 가입한 이메일 찾기 -> { emails } */
export const findId = (payload: FindIdPayload) =>
  api.post<FindIdResponse>("/auth/find-id/", payload).then((res) => res.data);

/** 이메일 + 휴대폰 인증 확인 -> { reset_token } (15분, 1회용) */
export const verifyPasswordReset = (payload: PasswordResetVerifyPayload) =>
  api
    .post<PasswordResetVerifyResponse>("/auth/password-reset/verify/", payload)
    .then((res) => res.data);

/** 새 비밀번호 저장 */
export const confirmPasswordReset = (payload: PasswordResetConfirmPayload) =>
  api.post<void>("/auth/password-reset/confirm/", payload);

/** 소셜 로그인. kakao: { code, redirect_uri } / naver: { code, state } */
export const socialLogin = (provider: SocialProvider, payload: SocialLoginPayload) =>
  api.post<AuthSession>(`/auth/${provider}/`, payload).then((res) => res.data);

/** 요청 실패 응답의 본문. 응답이 없는 네트워크 오류 등은 undefined. */
export function errorDataOf(error: unknown): ApiErrorData | undefined {
  return isAxiosError<ApiErrorData>(error) ? error.response?.data : undefined;
}

/** DRF의 필드 에러({field: [msg]})를 사람이 읽을 수 있는 문자열로 변환 */
export function toErrorMessage(error: unknown): string {
  const data = errorDataOf(error);
  if (!data) return "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
  if (typeof data === "string") return data;

  const flatten = (value: unknown): string => {
    if (Array.isArray(value)) return value.map(flatten).join(" ");
    if (value && typeof value === "object") return Object.values(value).map(flatten).join(" ");
    return String(value);
  };
  return flatten(data) || "요청을 처리하지 못했습니다.";
}

export default api;
