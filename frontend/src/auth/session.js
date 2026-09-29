/**
 * 로그인 세션(API 토큰 + 회원 정보) 저장소.
 * 브라우저를 닫아도 로그인이 유지되도록 localStorage에 둔다.
 */
const STORAGE_KEY = "pinroute.session";

export function getSession() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) ?? null;
  } catch {
    return null;
  }
}

/** 로그인·가입 API 응답({ token, user })을 그대로 저장한다. */
export function saveSession({ token, user }) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user }));
}

export function clearSession() {
  localStorage.removeItem(STORAGE_KEY);
}
