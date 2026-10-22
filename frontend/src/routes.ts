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
  /** 여행 상세. 뒤에 탭(expenses·checklist)이 붙을 수 있고, 없으면 여행 일정 탭 */
  TRIP_DETAIL: "/trips/:tripId/:tab?",
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

/** 여행 상세 탭: 여행 일정(기본) · 경비 관리 · 여행 체크리스트 · 여행 요약(여행 시작일부터) */
export type TripTab = "schedule" | "expenses" | "checklist" | "summary";

const TRIP_TAB_SEGMENTS: Record<TripTab, string> = {
  schedule: "",
  expenses: "/expenses",
  checklist: "/checklist",
  summary: "/summary",
};

/** "/trips/12/checklist" (여행 일정은 "/trips/12") */
export const tripTabPath = (tripId: number, tab: TripTab) => `${tripDetailPath(tripId)}${TRIP_TAB_SEGMENTS[tab]}`;

/** 주소의 탭 조각 -> 탭. 알 수 없는 조각이면 null */
export const tripTabFromSegment = (segment?: string): TripTab | null =>
  (Object.keys(TRIP_TAB_SEGMENTS) as TripTab[]).find((tab) => TRIP_TAB_SEGMENTS[tab] === (segment ? `/${segment}` : "")) ?? null;

const TRIP_INVITE_PREFIX = "/trips/invite/";

/** 초대 링크 주소 (카카오톡·복사로 나누므로 전체 URL) */
export const tripInviteUrl = (token: string) => `${window.location.origin}${TRIP_INVITE_PREFIX}${token}`;

/** 초대 링크로 들어온 경로인지 (로그인 화면 안내 문구용) */
export const isTripInvitePath = (path?: string) => Boolean(path?.startsWith(TRIP_INVITE_PREFIX));
