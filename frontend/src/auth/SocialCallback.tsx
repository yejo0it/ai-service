import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { linkSocialAccount, socialLogin, toErrorMessage } from "../api/client";
import FullScreenLoader from "../components/FullScreenLoader";
import { ROUTES, type MyPageLocationState } from "../routes";
import type { SocialLoginPayload } from "../types/api";
import type { LoginLocationState } from "./LoginPage";
import { consumePurpose, consumeReturnPath, consumeState, isSocialProvider, redirectUriOf } from "./oauth";
import { safeReturnPath } from "./returnPath";
import { getSession, saveSession } from "./session";

/**
 * `/auth/:provider/callback` — 카카오·네이버 인가 후 돌아오는 화면.
 * - 로그인: 인가 코드를 백엔드로 넘겨 로그인(없으면 자동 가입)하고 돌아갈 화면으로 보낸다.
 *   실패하면 로그인 화면으로 돌아가 에러를 보여준다.
 * - 계정 연결(마이페이지에서 시작): 지금 계정에 소셜 계정을 연결하고 마이페이지로 돌아가 결과를 토스트로 알린다.
 */
export default function SocialCallback() {
  const { provider } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  // 인가 코드는 한 번만 쓸 수 있으므로 StrictMode의 effect 재실행에서 다시 보내지 않는다.
  const started = useRef(false);
  const [linking, setLinking] = useState(false);

  useEffect(() => {
    if (started.current || !isSocialProvider(provider)) return;
    started.current = true;

    // 계정 연결은 로그인한 상태에서만 시작한다(로그아웃됐으면 로그인으로 처리하지 않고 실패로 돌려보낸다).
    const link = consumePurpose() === "link";
    setLinking(link);
    const fail = (error: string) => {
      if (link) {
        const state: MyPageLocationState = { toast: { ok: false, message: error } };
        navigate(ROUTES.MYPAGE, { replace: true, state });
        return;
      }
      const state: LoginLocationState = { error };
      navigate(ROUTES.LOGIN, { replace: true, state });
    };
    const code = params.get("code");
    const state = params.get("state");

    // 사용자가 동의 화면에서 취소한 경우 등
    if (params.get("error") || !code) {
      fail(link ? "계정 연결이 취소되었어요." : "소셜 로그인이 취소되었어요.");
      return;
    }
    if (!consumeState(state)) {
      fail("로그인 요청이 만료되었어요. 다시 시도해 주세요.");
      return;
    }

    const payload: SocialLoginPayload =
      provider === "kakao" ? { code, redirect_uri: redirectUriOf(provider) } : { code, state: state ?? "" };
    if (link) {
      const label = provider === "kakao" ? "카카오" : "네이버";
      linkSocialAccount(provider, payload)
        .then((user) => {
          const session = getSession();
          if (session) saveSession({ ...session, user });
          const state: MyPageLocationState = { toast: { ok: true, message: `${label} 계정이 연결되었습니다.` } };
          navigate(ROUTES.MYPAGE, { replace: true, state });
        })
        .catch((error) => fail(toErrorMessage(error)));
      return;
    }

    socialLogin(provider, payload)
      .then((session) => {
        saveSession(session);
        navigate(safeReturnPath(consumeReturnPath()), { replace: true });
      })
      .catch((error) => fail(toErrorMessage(error)));
  }, [provider, params, navigate]);

  if (!isSocialProvider(provider)) return <Navigate to={ROUTES.LOGIN} replace />;

  return <FullScreenLoader message={linking ? "계정을 연결하는 중이에요..." : "로그인하는 중이에요..."} />;
}
