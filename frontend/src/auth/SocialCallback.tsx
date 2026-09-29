import { useEffect, useRef } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { socialLogin, toErrorMessage } from "../api/client";
import { ROUTES } from "../routes";
import type { SocialLoginPayload } from "../types/api";
import type { LoginLocationState } from "./LoginPage";
import { consumeState, isSocialProvider, redirectUriOf } from "./oauth";
import { saveSession } from "./session";

/**
 * `/auth/:provider/callback` — 카카오·네이버 인가 후 돌아오는 화면.
 * 인가 코드를 백엔드로 넘겨 로그인(없으면 자동 가입)하고 온보딩으로 보낸다.
 * 실패하면 로그인 화면으로 돌아가 에러를 보여준다.
 */
export default function SocialCallback() {
  const { provider } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  // 인가 코드는 한 번만 쓸 수 있으므로 StrictMode의 effect 재실행에서 다시 보내지 않는다.
  const started = useRef(false);

  useEffect(() => {
    if (started.current || !isSocialProvider(provider)) return;
    started.current = true;

    const fail = (error: string) => {
      const state: LoginLocationState = { error };
      navigate(ROUTES.LOGIN, { replace: true, state });
    };
    const code = params.get("code");
    const state = params.get("state");

    // 사용자가 동의 화면에서 취소한 경우 등
    if (params.get("error") || !code) {
      fail("소셜 로그인이 취소되었어요.");
      return;
    }
    if (!consumeState(state)) {
      fail("로그인 요청이 만료되었어요. 다시 시도해 주세요.");
      return;
    }

    const payload: SocialLoginPayload =
      provider === "kakao" ? { code, redirect_uri: redirectUriOf(provider) } : { code, state: state ?? "" };
    socialLogin(provider, payload)
      .then((session) => {
        saveSession(session);
        navigate(ROUTES.HOME, { replace: true });
      })
      .catch((error) => fail(toErrorMessage(error)));
  }, [provider, params, navigate]);

  if (!isSocialProvider(provider)) return <Navigate to={ROUTES.LOGIN} replace />;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-white">
      <i className="fas fa-circle-notch fa-spin text-2xl text-indigo-500" aria-hidden="true" />
      <p className="text-sm text-slate-500">로그인하는 중이에요...</p>
    </div>
  );
}
