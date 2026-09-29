import { ROUTES } from "../routes";

/**
 * 로그인이 필요한 화면에서 로그인 화면으로 보낼 때, 원래 가려던 경로를 담는 라우터 state.
 * (LoginLocationState의 from과 같은 값)
 */
export interface ReturnPathState {
  from?: string;
}

/**
 * 로그인 후 돌아갈 경로. 앱 안의 경로("/..."로 시작, "//"·"/\\" 제외)만 허용해
 * 외부 사이트로 보내는 오픈 리다이렉트를 막는다. 없거나 허용되지 않으면 홈으로 보낸다.
 */
export function safeReturnPath(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/")) return ROUTES.HOME;
  if (value.startsWith("//") || value.startsWith("/\\")) return ROUTES.HOME;
  return value;
}
