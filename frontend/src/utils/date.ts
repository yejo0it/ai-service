/**
 * "YYYY-MM-DD" 날짜 문자열 도우미.
 * 여행 날짜는 시각이 없는 달력 날짜이므로 항상 로컬 자정 기준으로 다룬다(타임존 밀림 방지).
 */

const pad2 = (value: number) => String(value).padStart(2, "0");

export const WEEKDAYS_KO = ["일", "월", "화", "수", "목", "금", "토"] as const;

/** Date -> "2026-10-26" */
export const toISODate = (date: Date) =>
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;

/** "2026-10-26" -> 로컬 자정 Date */
export const parseISODate = (value: string) => new Date(`${value}T00:00:00`);

export const todayISODate = () => toISODate(new Date());

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** to - from 일수 ("2026-10-26" → "2026-10-30" = 4). 서머타임과 무관하게 달력 날짜로 센다. */
export function diffDays(from: string, to: string): number {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / 86_400_000);
}

/** "2026-10-26" -> "10월 26일 (월)" */
export function formatMonthDay(value: string): string {
  const date = parseISODate(value);
  return `${date.getMonth() + 1}월 ${date.getDate()}일 (${WEEKDAYS_KO[date.getDay()]})`;
}

/** "2026-10-26" -> "10.26" */
export function formatShortDot(value: string): string {
  const date = parseISODate(value);
  return `${date.getMonth() + 1}.${date.getDate()}`;
}

/** 해당 달을 덮는 6주(일요일 시작) 달력. 각 주는 Date 7개. */
export function monthWeeks(year: number, month: number): Date[][] {
  const first = new Date(year, month, 1);
  const start = addDays(first, -first.getDay());
  return Array.from({ length: 6 }, (_, week) =>
    Array.from({ length: 7 }, (_, day) => addDays(start, week * 7 + day)),
  );
}
