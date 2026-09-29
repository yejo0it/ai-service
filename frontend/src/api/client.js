import axios from "axios";
import { clearSession, getSession } from "../auth/session";

const api = axios.create({
  baseURL: import.meta.env?.VITE_API_URL ?? "http://localhost:8003/api/v1",
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
api.interceptors.response.use(undefined, (error) => {
  if (error?.response?.status === 401 && getSession()) clearSession();
  return Promise.reject(error);
});

/** 항공사 목록 조회 */
export const getAirlines = () =>
  api.get("/airlines/").then((res) => res.data);

/** 온보딩 Step 1~3을 한 번에 저장 (hotels 포함 가능) */
export const createTrip = (payload) =>
  api.post("/trips/", payload).then((res) => res.data);

/** 단계별 저장이 필요할 때: Step 3만 따로 저장 */
export const createHotel = (tripId, payload) =>
  api.post(`/trips/${tripId}/hotels/`, payload).then((res) => res.data);

/**
 * 숙소 자동완성 (Google Places). sessionToken은 숙소 입력 세션마다 만든 UUID로,
 * 같은 토큰으로 getHotelDetails를 호출하면 세션이 끝나 자동완성 요청이 과금되지 않는다.
 */
export const searchHotels = ({ input, sessionToken, city, cityCode }) =>
  api
    .get("/places/hotels/", {
      params: { input, session_token: sessionToken, city, city_code: cityCode },
    })
    .then((res) => res.data);

/** 선택한 숙소의 주소·좌표 */
export const getHotelDetails = (placeId, sessionToken) =>
  api
    .get(`/places/hotels/${encodeURIComponent(placeId)}/`, {
      params: { session_token: sessionToken },
    })
    .then((res) => res.data);

/* ------------------------------------------------------------------ *
 * 회원 (로그인 · 가입)
 * 로그인·가입·소셜 로그인은 모두 { token, user }를 돌려준다.
 * ------------------------------------------------------------------ */

export const login = (payload) => api.post("/auth/login/", payload).then((res) => res.data);

export const signup = (payload) => api.post("/auth/signup/", payload).then((res) => res.data);

/** 가입 가능한 이메일인지 -> { available } */
export const checkEmail = (email) =>
  api.post("/auth/check-email/", { email }).then((res) => res.data);

/** 인증번호 발송 -> { expires_in, debug_code? } (debug_code는 개발 서버에서만) */
export const requestPhoneCode = (phone) =>
  api.post("/auth/phone/request/", { phone }).then((res) => res.data);

/** 인증번호 확인 -> { verification_token } */
export const verifyPhoneCode = (phone, code) =>
  api.post("/auth/phone/verify/", { phone, code }).then((res) => res.data);

/** 서버의 API 토큰 폐기 (useLogout에서 세션 삭제와 함께 쓴다) */
export const logout = () => api.post("/auth/logout/");

/** 휴대폰 인증 후 가입한 이메일 찾기 -> { emails } */
export const findId = (payload) => api.post("/auth/find-id/", payload).then((res) => res.data);

/** 이메일 + 휴대폰 인증 확인 -> { reset_token } (15분, 1회용) */
export const verifyPasswordReset = (payload) =>
  api.post("/auth/password-reset/verify/", payload).then((res) => res.data);

/** 새 비밀번호 저장 { reset_token, password, password_confirm } */
export const confirmPasswordReset = (payload) => api.post("/auth/password-reset/confirm/", payload);

/** 소셜 로그인. kakao: { code, redirect_uri } / naver: { code, state } */
export const socialLogin = (provider, payload) =>
  api.post(`/auth/${provider}/`, payload).then((res) => res.data);

/** DRF의 필드 에러({field: [msg]})를 사람이 읽을 수 있는 문자열로 변환 */
export function toErrorMessage(error) {
  const data = error?.response?.data;
  if (!data) return "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
  if (typeof data === "string") return data;

  const flatten = (value) => {
    if (Array.isArray(value)) return value.map(flatten).join(" ");
    if (value && typeof value === "object")
      return Object.values(value).map(flatten).join(" ");
    return String(value);
  };
  return flatten(data) || "요청을 처리하지 못했습니다.";
}

export default api;
