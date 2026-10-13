/**
 * 카카오·네이버 OAuth 2.0 인가 요청.
 * 인가 페이지로 이동했다가 /auth/{provider}/callback 으로 돌아오면 SocialCallback이
 * 인가 코드를 백엔드로 넘긴다.
 * - login: `POST /auth/{provider}/` 로그인/자동 가입
 * - link: `POST /auth/me/social/{provider}/` 마이페이지에서 지금 계정에 연결
 */

import type { SocialProvider } from "../types/api";

const CLIENT_IDS: Record<SocialProvider, string> = {
  kakao: import.meta.env.VITE_KAKAO_REST_API_KEY ?? "",
  naver: import.meta.env.VITE_NAVER_CLIENT_ID ?? "",
};

const AUTHORIZE_URLS: Record<SocialProvider, string> = {
  kakao: "https://kauth.kakao.com/oauth/authorize",
  naver: "https://nid.naver.com/oauth2.0/authorize",
};

// CSRF 방지용 state. 돌아왔을 때 같은 값인지 확인한다.
const STATE_KEY = "pinroute.oauth-state";
// 인가 페이지를 다녀오는 동안 로그인 후 돌아갈 경로를 보관한다.
const RETURN_PATH_KEY = "pinroute.oauth-return";
// 로그인인지, 마이페이지 계정 연결인지
const PURPOSE_KEY = "pinroute.oauth-purpose";

export type SocialAuthPurpose = "login" | "link";

// 이미 로그인되어 있어도 소셜 로그인 화면을 다시 띄우는 인가 파라미터
const RELOGIN_PARAMS: Record<SocialProvider, [string, string]> = {
  kakao: ["prompt", "login"],
  naver: ["auth_type", "reauthenticate"],
};

export const SOCIAL_PROVIDERS: readonly SocialProvider[] = ["kakao", "naver"];

export const isSocialProvider = (value: unknown): value is SocialProvider =>
  SOCIAL_PROVIDERS.includes(value as SocialProvider);

export const redirectUriOf = (provider: SocialProvider) =>
  `${window.location.origin}/auth/${provider}/callback`;

export const isSocialLoginConfigured = (provider: SocialProvider) => Boolean(CLIENT_IDS[provider]);

export function startSocialLogin(
  provider: SocialProvider,
  returnPath?: string,
  purpose: SocialAuthPurpose = "login",
): void {
  const state = crypto.randomUUID();
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(PURPOSE_KEY, purpose);
  if (returnPath) sessionStorage.setItem(RETURN_PATH_KEY, returnPath);
  else sessionStorage.removeItem(RETURN_PATH_KEY);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: CLIENT_IDS[provider],
    redirect_uri: redirectUriOf(provider),
    state,
  });
  // 계정 연결은 브라우저에 로그인된 소셜 계정으로 바로 넘어가지 않고 로그인 화면을 항상 띄워
  // 어떤 계정을 연결하는지 직접 고르게 한다.
  if (purpose === "link") params.set(...RELOGIN_PARAMS[provider]);
  window.location.assign(`${AUTHORIZE_URLS[provider]}?${params}`);
}

/** 소셜 로그인 전에 기억해 둔 돌아갈 경로를 꺼내고 지운다. */
export function consumeReturnPath(): string | null {
  const returnPath = sessionStorage.getItem(RETURN_PATH_KEY);
  sessionStorage.removeItem(RETURN_PATH_KEY);
  return returnPath;
}

/** 인가를 시작할 때 기억해 둔 목적(로그인/계정 연결)을 꺼내고 지운다. */
export function consumePurpose(): SocialAuthPurpose {
  const purpose = sessionStorage.getItem(PURPOSE_KEY);
  sessionStorage.removeItem(PURPOSE_KEY);
  return purpose === "link" ? "link" : "login";
}

/** 돌아온 state가 요청 때 저장한 값과 같은지 확인하고, 저장값은 지운다. */
export function consumeState(state: string | null): boolean {
  const expected = sessionStorage.getItem(STATE_KEY);
  sessionStorage.removeItem(STATE_KEY);
  return Boolean(state) && state === expected;
}
