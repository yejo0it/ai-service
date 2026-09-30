/**
 * 로그인 세션(API 토큰 + 회원 정보) 저장소.
 * 브라우저를 닫아도 로그인이 유지되도록 localStorage에 둔다.
 *
 * 저장·삭제할 때 구독자(AuthProvider)에게 알린다. 그래서 로그인 화면의 saveSession,
 * 로그아웃·401 인터셉터의 clearSession이 곧바로 화면의 인증 상태(useAuth)에 반영된다.
 */
import type { AuthSession } from "../types/api";

export const STORAGE_KEY = "pinroute.session";

type SessionListener = (session: AuthSession | null) => void;

const listeners = new Set<SessionListener>();

const notify = (session: AuthSession | null) => listeners.forEach((listener) => listener(session));

/** 세션이 바뀔 때마다 호출된다. 구독 해제 함수를 돌려준다. */
export function subscribeSession(listener: SessionListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

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
  const session = { token, user };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  notify(session);
}

export function clearSession(): void {
  localStorage.removeItem(STORAGE_KEY);
  notify(null);
}
