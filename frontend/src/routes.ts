/**
 * 화면 경로. 홈 화면 주소가 바뀌면 HOME만 고치면 로그인·가입·로그아웃 이동이 모두 따라간다.
 */
export const ROUTES = {
  HOME: "/",
  ONBOARDING: "/onboarding",
  MY_TRIPS: "/trips",
  TRIP_DETAIL: "/trips/:tripId",
  LOGIN: "/login",
  SIGNUP: "/signup",
  FIND_ID: "/find-id",
  RESET_PASSWORD: "/reset-password",
  RESET_PASSWORD_NEW: "/reset-password/new",
  SOCIAL_CALLBACK: "/auth/:provider/callback",
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];

/** "/trips/12" */
export const tripDetailPath = (tripId: number) => `/trips/${tripId}`;
