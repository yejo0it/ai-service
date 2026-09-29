/**
 * 로그인 세션(API 토큰 + 회원 정보) 저장소.
 * 브라우저를 닫아도 로그인이 유지되도록 localStorage에 둔다.
 */
import type { AuthSession } from "../types/api";

const STORAGE_KEY = "pinroute.session";

export function getSession(): AuthSession | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? (JSON.parse(stored) as AuthSession) : null;
  } catch {
    return null;
  }
}

/** 로그인·가입 API 응답({ token, user })을 그대로 저장한다. */
export function saveSession({ token, user }: AuthSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, user }));
}

export function clearSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}
