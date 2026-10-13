/**
 * 화면 경로. 홈 화면 주소가 바뀌면 HOME만 고치면 로그인·가입·로그아웃 이동이 모두 따라간다.
 */
export const ROUTES = {
  HOME: "/",
  /** 예전 새 여행 만들기 주소. 홈으로 보내 새 여행 만들기 모달을 연다. */
  ONBOARDING: "/onboarding",
  MY_TRIPS: "/trips",
  PACKING: "/packing",
  MYPAGE: "/mypage",
  TRIP_DETAIL: "/trips/:tripId",
  TRIP_INVITE: "/trips/invite/:token",
  LOGIN: "/login",
  SIGNUP: "/signup",
  FIND_ID: "/find-id",
  RESET_PASSWORD: "/reset-password",
  RESET_PASSWORD_NEW: "/reset-password/new",
  SOCIAL_CALLBACK: "/auth/:provider/callback",
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];

/** 마이페이지로 이동하며 결과 토스트를 띄울 때 넘기는 라우터 state (소셜 계정 연결 등) */
export interface MyPageLocationState {
  toast?: { ok: boolean; message: string };
}

/** 홈으로 이동하며 새 여행 만들기 모달을 열 때 넘기는 라우터 state */
export interface HomeLocationState {
  newTrip?: boolean;
}

/** "/trips/12" */
export const tripDetailPath = (tripId: number) => `/trips/${tripId}`;

const TRIP_INVITE_PREFIX = "/trips/invite/";

/** 초대 링크 주소 (카카오톡·복사로 나누므로 전체 URL) */
export const tripInviteUrl = (token: string) => `${window.location.origin}${TRIP_INVITE_PREFIX}${token}`;

/** 초대 링크로 들어온 경로인지 (로그인 화면 안내 문구용) */
export const isTripInvitePath = (path?: string) => Boolean(path?.startsWith(TRIP_INVITE_PREFIX));
