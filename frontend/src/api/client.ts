import axios, { isAxiosError } from "axios";
import { clearSession, getSession } from "../auth/session";
import type {
  Airline,
  ApiErrorData,
  AuthSession,
  AuthUser,
  CheckEmailResponse,
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
