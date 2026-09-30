import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import type { ReturnPathState } from "../auth/returnPath";
import { ROUTES } from "../routes";
import FullScreenLoader from "./FullScreenLoader";

interface ProtectedRouteProps {
  /** 없으면 중첩 라우트(<Outlet />)를 렌더링한다. */
  children?: ReactNode;
}

/**
 * 로그인해야 볼 수 있는 화면.
 * - 토큰 확인 중: 로딩 화면(보호 화면이나 로그인 화면이 잠깐 보이는 깜빡임 방지)
 * - 미로그인: 로그인 화면으로 보내고, 원래 경로를 state.from에 담아 로그인 후 돌아오게 한다.
 * - 로그인 중 토큰이 만료(401)되어 세션이 지워져도 같은 경로로 로그인 화면에 간다.
 */
export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "checking") return <FullScreenLoader />;
  if (status === "unauthenticated") {
    const state: ReturnPathState = {
      from: `${location.pathname}${location.search}${location.hash}`,
    };
    return <Navigate to={ROUTES.LOGIN} replace state={state} />;
  }
  return children ?? <Outlet />;
}
