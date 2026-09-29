import type { Trip, TripColorKey } from "../types/api";
import { diffDays } from "../utils/date";

export type TripStatus = "upcoming" | "ongoing" | "past";

export function tripStatus(trip: Trip, today: string): TripStatus {
  if (today < trip.start_date) return "upcoming";
  if (today > trip.end_date) return "past";
  return "ongoing";
}

/** "D-15" · "D-DAY" · "여행 중" · "다녀옴" */
export function dDayLabel(trip: Trip, today: string): string {
  const status = tripStatus(trip, today);
  if (status === "past") return "다녀옴";
  if (status === "ongoing") return today === trip.start_date ? "D-DAY" : "여행 중";
  return `D-${diffDays(today, trip.start_date)}`;
}

/** 여행 도시 이름 목록 (빈 이름 제외) */
export const tripCities = (trip: Trip) => trip.destinations.map((dest) => dest.city).filter(Boolean);

/** 캘린더 뱃지처럼 좁은 곳에 쓰는 이름: "도쿄" · "도쿄 외 2곳" */
export function tripShortTitle(trip: Trip): string {
  const cities = tripCities(trip);
  if (cities.length === 0) return "여행";
  return cities.length === 1 ? cities[0] : `${cities[0]} 외 ${cities.length - 1}곳`;
}

/** 진행 중인 여행이 있으면 그 여행, 없으면 가장 가까운 다가오는 여행 */
export function nextTrip(trips: Trip[], today: string): Trip | null {
  const ongoing = trips.find((trip) => tripStatus(trip, today) === "ongoing");
  if (ongoing) return ongoing;
  return (
    trips
      .filter((trip) => tripStatus(trip, today) === "upcoming")
      .sort((a, b) => a.start_date.localeCompare(b.start_date))[0] ?? null
  );
}

/**
 * 여행별 고유 색. Tailwind는 클래스 문자열을 그대로 찾아 CSS를 만들므로
 * 동적으로 조합하지 않고 완성된 클래스를 나열해 둔다.
 */
export interface TripColor {
  /** 색 이름 (색 선택 버튼 라벨) */
  label: string;
  /** 캘린더 날짜 줄의 기간 띠 */
  band: string;
  /** 선택된 여행의 기간 띠 */
  bandSelected: string;
  /** 시작일·종료일 원 (배경 + 글자색) */
  cap: string;
  /** 기간 안 날짜 숫자 */
  text: string;
  /** 제목 뱃지 */
  badge: string;
  /** 다른 여행과 겹칠 때 아래 줄에 그리는 막대 */
  bar: string;
  barSelected: string;
  /** 목록·범례의 점 */
  dot: string;
}

/**
 * 여행 색상 팔레트: 기본 색상 + 서비스 대표색(인디고)의 파스텔 톤. 키는 백엔드 Trip.color와 같다.
 * 시작·종료일 원도 연한 색(200) 위에 같은 계열의 진한 글자를 써서 흰 글자보다 부드럽게 보이게 한다.
 * Tailwind는 클래스 문자열을 그대로 찾아 CSS를 만들므로 완성된 클래스를 나열해 둔다.
 */
export const TRIP_COLORS: Record<TripColorKey, TripColor> = {
  indigo: {
    label: "인디고",
    band: "bg-indigo-50", bandSelected: "bg-indigo-100", cap: "bg-indigo-200 text-indigo-800", text: "text-indigo-600",
    badge: "bg-indigo-50 text-indigo-700 ring-indigo-200", bar: "bg-indigo-50 text-indigo-700",
    barSelected: "bg-indigo-200 text-indigo-800 ring-indigo-300", dot: "bg-indigo-300",
  },
  red: {
    label: "빨강",
    band: "bg-rose-50", bandSelected: "bg-rose-100", cap: "bg-rose-200 text-rose-800", text: "text-rose-600",
    badge: "bg-rose-50 text-rose-700 ring-rose-200", bar: "bg-rose-50 text-rose-700",
    barSelected: "bg-rose-200 text-rose-800 ring-rose-300", dot: "bg-rose-300",
  },
  orange: {
    label: "주황",
    band: "bg-orange-50", bandSelected: "bg-orange-100", cap: "bg-orange-200 text-orange-800", text: "text-orange-600",
    badge: "bg-orange-50 text-orange-700 ring-orange-200", bar: "bg-orange-50 text-orange-700",
    barSelected: "bg-orange-200 text-orange-800 ring-orange-300", dot: "bg-orange-300",
  },
  yellow: {
    label: "노랑",
    band: "bg-amber-50", bandSelected: "bg-amber-100", cap: "bg-amber-200 text-amber-800", text: "text-amber-600",
    badge: "bg-amber-50 text-amber-700 ring-amber-200", bar: "bg-amber-50 text-amber-700",
    barSelected: "bg-amber-200 text-amber-800 ring-amber-300", dot: "bg-amber-300",
  },
  green: {
    label: "초록",
    band: "bg-emerald-50", bandSelected: "bg-emerald-100", cap: "bg-emerald-200 text-emerald-800", text: "text-emerald-600",
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-200", bar: "bg-emerald-50 text-emerald-700",
    barSelected: "bg-emerald-200 text-emerald-800 ring-emerald-300", dot: "bg-emerald-300",
  },
  blue: {
    label: "파랑",
    band: "bg-sky-50", bandSelected: "bg-sky-100", cap: "bg-sky-200 text-sky-800", text: "text-sky-600",
    badge: "bg-sky-50 text-sky-700 ring-sky-200", bar: "bg-sky-50 text-sky-700",
    barSelected: "bg-sky-200 text-sky-800 ring-sky-300", dot: "bg-sky-300",
  },
  purple: {
    label: "보라",
    band: "bg-violet-50", bandSelected: "bg-violet-100", cap: "bg-violet-200 text-violet-800", text: "text-violet-600",
    badge: "bg-violet-50 text-violet-700 ring-violet-200", bar: "bg-violet-50 text-violet-700",
    barSelected: "bg-violet-200 text-violet-800 ring-violet-300", dot: "bg-violet-300",
  },
  gray: {
    label: "회색",
    band: "bg-slate-50", bandSelected: "bg-slate-100", cap: "bg-slate-200 text-slate-800", text: "text-slate-600",
    badge: "bg-slate-50 text-slate-700 ring-slate-200", bar: "bg-slate-50 text-slate-700",
    barSelected: "bg-slate-200 text-slate-800 ring-slate-300", dot: "bg-slate-300",
  },
};

/** 색 선택 순서 (대표색 인디고 먼저) */
export const TRIP_COLOR_KEYS = Object.keys(TRIP_COLORS) as TripColorKey[];

/** 색을 고르지 않은 여행의 자동 색. 연달아 만든 여행(id가 이웃)이 겹쳐도 구분되게 섞어 둔다. */
const AUTO_ORDER: TripColorKey[] = ["indigo", "green", "orange", "blue", "red", "purple", "yellow", "gray"];

export const tripColor = (trip: Trip): TripColor =>
  TRIP_COLORS[trip.color || AUTO_ORDER[trip.id % AUTO_ORDER.length]];
