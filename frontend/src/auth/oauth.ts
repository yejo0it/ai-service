/**
 * 카카오·네이버 OAuth 2.0 인가 요청.
 * 인가 페이지로 이동했다가 /auth/{provider}/callback 으로 돌아오면 SocialCallback이
 * 인가 코드를 백엔드(`POST /auth/{provider}/`)로 넘겨 로그인/자동 가입을 마친다.
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

export const SOCIAL_PROVIDERS: readonly SocialProvider[] = ["kakao", "naver"];

export const isSocialProvider = (value: unknown): value is SocialProvider =>
  SOCIAL_PROVIDERS.includes(value as SocialProvider);

export const redirectUriOf = (provider: SocialProvider) =>
  `${window.location.origin}/auth/${provider}/callback`;

export const isSocialLoginConfigured = (provider: SocialProvider) => Boolean(CLIENT_IDS[provider]);

export function startSocialLogin(provider: SocialProvider): void {
  const state = crypto.randomUUID();
  sessionStorage.setItem(STATE_KEY, state);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: CLIENT_IDS[provider],
    redirect_uri: redirectUriOf(provider),
    state,
  });
  window.location.assign(`${AUTHORIZE_URLS[provider]}?${params}`);
}

/** 돌아온 state가 요청 때 저장한 값과 같은지 확인하고, 저장값은 지운다. */
export function consumeState(state: string | null): boolean {
  const expected = sessionStorage.getItem(STATE_KEY);
  sessionStorage.removeItem(STATE_KEY);
  return Boolean(state) && state === expected;
}
