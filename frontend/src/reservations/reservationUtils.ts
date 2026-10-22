import type {
  FlightBooking,
  FlightSegmentData,
  HotelBooking,
  HotelStayData,
  ReservationIssue,
} from "../types/api";

/** 예약 정보 편집 도우미. 분석 결과와 사용자가 고친 값은 같은 객체 모양이라 경로(path)로 읽고 쓴다. */

export const EMPTY_SEGMENT: FlightSegmentData = {
  airline_name: null,
  flight_number: null,
  departure_airport_code: null,
  departure_airport_name: null,
  arrival_airport_code: null,
  arrival_airport_name: null,
  departure_date: null,
  departure_time: null,
  arrival_date: null,
  arrival_time: null,
  direction: null,
  notes: [],
};

export const EMPTY_STAY: HotelStayData = {
  name: null,
  address: null,
  check_in_date: null,
  check_out_date: null,
  check_in_time: null,
  check_out_time: null,
  status: null,
  notes: [],
};

/** 직접 입력으로 시작할 때의 빈 예약 정보(칸이 하나씩 있다) */
export const emptyFlight = (): FlightBooking => ({ itineraries: [{ status: null, segments: [{ ...EMPTY_SEGMENT }] }] });
export const emptyHotel = (): HotelBooking => ({ stays: [{ ...EMPTY_STAY }] });

type Json = Record<string, unknown> | unknown[];

/** "itineraries.0.segments.1.departure_date" 같은 경로의 값 */
export function getByPath(root: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, key) => (node == null ? undefined : (node as Record<string, unknown>)[key]), root);
}

/** 경로의 값을 바꾼 새 객체(원본은 그대로). 다른 칸은 건드리지 않아 사용자가 고친 값이 덮어써지지 않는다. */
export function setByPath<T>(root: T, path: string, value: unknown): T {
  const keys = path.split(".");
  const update = (node: unknown, index: number): unknown => {
    const key = keys[index];
    const copy: Json = Array.isArray(node) ? [...node] : { ...(node as Record<string, unknown>) };
    (copy as Record<string, unknown>)[key] = index === keys.length - 1 ? value : update((node as Record<string, unknown>)[key], index + 1);
    return copy;
  };
  return update(root, 0) as T;
}

/** 칸의 상태: 비어 있음(확인 필요) · 추출한 값 그대로 · 추출한 값을 고침 · 비어 있던 칸을 직접 입력 */
export type FieldState = "missing" | "extracted" | "edited" | "entered";

export function fieldState(original: unknown, current: unknown): FieldState {
  const now = typeof current === "string" ? current.trim() : "";
  const before = typeof original === "string" ? original.trim() : "";
  if (!now) return "missing";
  if (!before) return "entered";
  return now === before ? "extracted" : "edited";
}

/** 경로 -> 첫 번째 메시지 */
export function issueMap(issues: ReservationIssue[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const issue of issues) if (!map.has(issue.path)) map.set(issue.path, issue.message);
  return map;
}

/** 입력 칸의 문자열 -> 저장할 값(비면 null, 앞뒤 공백 제거) */
export const toValue = (text: string): string | null => text.trim() || null;
