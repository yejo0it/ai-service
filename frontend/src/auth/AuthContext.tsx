import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { isAxiosError } from "axios";
import { getMe } from "../api/client";
import type { AuthUser } from "../types/api";
import { STORAGE_KEY, getSession, saveSession, subscribeSession } from "./session";

/**
 * checking: 저장된 토큰을 서버에서 확인하는 중(앱 첫 로드)
 * authenticated: 로그인됨 / unauthenticated: 로그인 안 됨
 */
export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

export interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * 앱 전체의 인증 상태.
 * - 저장된 세션이 있으면 첫 로드 때 `/auth/me/`로 토큰을 확인한다. 만료·폐기(401)면 API 인터셉터가
 *   세션을 지우고, 네트워크 오류 등으로 확인하지 못하면 저장된 세션을 그대로 믿는다.
 * - saveSession / clearSession 호출(로그인·로그아웃·401)과 다른 탭의 변경을 구독해 즉시 반영한다.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getSession()?.user ?? null);
  const [status, setStatus] = useState<AuthStatus>(() =>
    getSession() ? "checking" : "unauthenticated",
  );

  useEffect(() => {
    const apply = () => {
      const session = getSession();
      setUser(session?.user ?? null);
      setStatus(session ? "authenticated" : "unauthenticated");
    };
    const unsubscribe = subscribeSession(apply);
    // 다른 탭에서 로그인·로그아웃하면 이 탭도 따라간다.
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) apply();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      unsubscribe();
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  useEffect(() => {
    const session = getSession();
    if (!session) return;
    let cancelled = false;
    getMe()
      .then((me) => {
        // 최신 회원 정보로 갱신한다(구독으로 authenticated가 된다).
        if (!cancelled && getSession()?.token === session.token) saveSession({ ...session, user: me });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // 401이면 인터셉터가 이미 세션을 지웠다(구독으로 unauthenticated가 된다).
        if (isAxiosError(error) && error.response?.status === 401) return;
        setStatus(getSession() ? "authenticated" : "unauthenticated");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({ status, user }), [status, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth는 <AuthProvider> 안에서만 사용할 수 있습니다.");
  return context;
}
