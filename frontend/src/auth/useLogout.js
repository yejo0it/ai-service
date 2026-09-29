import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "../api/client";
import { ROUTES } from "../routes";
import { clearSession } from "./session";

/**
 * 로그아웃: 서버 토큰 폐기 → 저장된 세션 삭제 → 로그인 화면으로 이동.
 * 서버 요청이 실패해도(네트워크 오류, 이미 만료된 토큰) 브라우저 쪽 세션은 반드시 지운다.
 */
export default function useLogout() {
  const navigate = useNavigate();
  return useCallback(async () => {
    try {
      await logout();
    } catch {
      // 토큰은 아래에서 지우므로 서버 실패는 무시한다.
    }
    clearSession();
    navigate(ROUTES.LOGIN, { replace: true });
  }, [navigate]);
}
