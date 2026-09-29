import type { Trip } from "../types/api";
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
  /** 캘린더 기간 막대 */
  bar: string;
  /** 선택된 막대 */
  barSelected: string;
  /** 목록·범례의 점 */
  dot: string;
}

const TRIP_COLORS: TripColor[] = [
  { bar: "bg-indigo-100 text-indigo-800", barSelected: "bg-indigo-600 text-white", dot: "bg-indigo-500" },
  { bar: "bg-emerald-100 text-emerald-800", barSelected: "bg-emerald-600 text-white", dot: "bg-emerald-500" },
  { bar: "bg-amber-100 text-amber-800", barSelected: "bg-amber-500 text-white", dot: "bg-amber-500" },
  { bar: "bg-sky-100 text-sky-800", barSelected: "bg-sky-600 text-white", dot: "bg-sky-500" },
  { bar: "bg-rose-100 text-rose-800", barSelected: "bg-rose-600 text-white", dot: "bg-rose-500" },
  { bar: "bg-violet-100 text-violet-800", barSelected: "bg-violet-600 text-white", dot: "bg-violet-500" },
];

export const tripColor = (trip: Trip): TripColor => TRIP_COLORS[trip.id % TRIP_COLORS.length];
