import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { safeReturnPath, type ReturnPathState } from "../auth/returnPath";
import FullScreenLoader from "./FullScreenLoader";

interface GuestOnlyRouteProps {
  /** 없으면 중첩 라우트(<Outlet />)를 렌더링한다. */
  children?: ReactNode;
}

/**
 * 로그인하지 않은 사용자만 보는 화면(로그인·회원가입).
 * 이미 로그인했으면 원래 가려던 경로(state.from) 또는 홈으로 보낸다.
 * 로그인 폼 제출로 로그인되는 순간에도 같은 경로로 이동하므로 LoginPage의 이동과 어긋나지 않는다.
 */
export default function GuestOnlyRoute({ children }: GuestOnlyRouteProps) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "checking") return <FullScreenLoader />;
  if (status === "authenticated") {
    const from = (location.state as ReturnPathState | null)?.from;
    return <Navigate to={safeReturnPath(from)} replace />;
  }
  return children ?? <Outlet />;
}
