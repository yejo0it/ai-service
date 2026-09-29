/**
 * 화면 경로. 홈 화면 주소가 바뀌면 HOME만 고치면 로그인·가입·로그아웃 이동이 모두 따라간다.
 * (지금은 온보딩이 홈 역할을 한다.)
 */
export const ROUTES = {
  HOME: "/onboarding",
  LOGIN: "/login",
  SIGNUP: "/signup",
  FIND_ID: "/find-id",
  RESET_PASSWORD: "/reset-password",
  RESET_PASSWORD_NEW: "/reset-password/new",
  SOCIAL_CALLBACK: "/auth/:provider/callback",
};
