import { findAirport } from "../onboarding/airports";
import { findCityByCode } from "../onboarding/cities";
import type { Airport, Hotel, Trip } from "../types/api";
import { addDays, parseISODate, toISODate } from "../utils/date";

export type StopKind = "airport" | "hotel" | "city";

/** 일정 카드 안의 위치 하나. 좌표가 있으면 지도 핀(번호)이 된다. */
export interface Stop {
  kind: StopKind;
  /** 출발·도착·체크인 등 */
  caption: string;
  label: string;
  lat?: number;
  lng?: number;
}

export type ItineraryKind = "flight" | "hotel" | "place";

/** 일정 카드 한 장 */
export interface ItineraryItem {
  id: string;
  kind: ItineraryKind;
  title: string;
  /** 오른쪽 위 표기 (시각 또는 체크인·숙박·체크아웃) */
  time: string;
  subtitle?: string;
  stops: Stop[];
}

export interface TripDay {
  /** 0부터 (0 = 첫째 날) */
  index: number;
  /** "YYYY-MM-DD" */
  date: string;
  items: ItineraryItem[];
}

/** 지도에 찍는 번호 핀 */
export interface RoutePoint {
  order: number;
  kind: StopKind;
  label: string;
  lat: number;
  lng: number;
}

const ORDINALS = ["첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째", "일곱째", "여덟째", "아홉째", "열째"];

/** 0 -> "첫째 날", 10 -> "11일차" */
export const dayLabel = (index: number) => (ORDINALS[index] ? `${ORDINALS[index]} 날` : `${index + 1}일차`);

const airportStop = (airport: Airport | null | undefined, caption: string): Stop => {
  const found = airport ? findAirport(airport.code, airport.name) : undefined;
  return {
    kind: "airport",
    caption,
    label: airport?.name ?? "공항 미지정",
    lat: found?.lat,
    lng: found?.lng,
  };
};

const hotelStop = (hotel: Hotel, caption: string): Stop => ({
  kind: "hotel",
  caption,
  label: hotel.address || hotel.name,
  lat: hotel.latitude ?? undefined,
  lng: hotel.longitude ?? undefined,
});

const hotelItem = (hotel: Hotel, id: string, time: string, subtitle?: string): ItineraryItem => ({
  id,
  kind: "hotel",
  title: hotel.name,
  time,
  subtitle,
  stops: [hotelStop(hotel, time)],
});

/**
 * 여행 기간을 날짜별로 나누고, 각 날짜에 이미 등록된 항공편·숙소를 일정 카드로 만든다.
 * - 가는 편: 출국일 / 오는 편: 귀국일
 * - 숙소: 체크인 날(체크인), 사이 날(숙박), 체크아웃 날(체크아웃)
 * 하루 안의 순서: 체크아웃 → 가는 편 → 숙박 → 체크인 → 오는 편
 */
export function tripDays(trip: Trip): TripDay[] {
  const flight = trip.flight_info;
  const departureDate = flight?.departure_at?.slice(0, 10) || trip.start_date;
  const returnDate = flight?.return_arrival_at?.slice(0, 10) || trip.end_date;
  const hotels = [...trip.hotels].sort((a, b) => a.check_in.localeCompare(b.check_in));

  const days: TripDay[] = [];
  for (let date = parseISODate(trip.start_date), index = 0; toISODate(date) <= trip.end_date; date = addDays(date, 1), index += 1) {
    const iso = toISODate(date);
    const items: ItineraryItem[] = [];

    hotels
      .filter((hotel) => hotel.check_out === iso && hotel.check_in !== iso)
      .forEach((hotel) => items.push(hotelItem(hotel, `hotel-${hotel.id}-out`, "체크아웃")));

    if (flight && iso === departureDate) {
      items.push({
        id: "flight-out",
        kind: "flight",
        title: `가는 편${flight.flight_number ? ` · ${flight.flight_number}` : ""}`,
        time: flight.departure_at?.slice(11, 16) ?? "",
        stops: [airportStop(flight.departure_airport, "출발"), airportStop(flight.arrival_airport, "도착")],
      });
    }

    hotels
      .filter((hotel) => hotel.check_in < iso && hotel.check_out !== null && iso < hotel.check_out)
      .forEach((hotel) => items.push(hotelItem(hotel, `hotel-${hotel.id}-stay-${iso}`, "숙박")));

    hotels
      .filter((hotel) => hotel.check_in === iso)
      .forEach((hotel) =>
        items.push(
          hotelItem(hotel, `hotel-${hotel.id}-in`, "체크인", hotel.nights ? `${hotel.nights}박` : undefined),
        ),
      );

    if (flight && iso === returnDate && (flight.return_flight_number || flight.return_arrival_at)) {
      items.push({
        id: "flight-return",
        kind: "flight",
        title: `오는 편${flight.return_flight_number ? ` · ${flight.return_flight_number}` : ""}`,
        time: flight.return_arrival_at?.slice(11, 16) ?? "",
        stops: [
          airportStop(flight.return_departure_airport, "출발"),
          airportStop(flight.return_arrival_airport, "도착"),
        ],
      });
    }

    days.push({ index, date: iso, items });
  }
  return days;
}

/** 카드 안 위치의 키 (번호 조회용) */
export const stopKey = (itemId: string, stopIndex: number) => `${itemId}:${stopIndex}`;

/**
 * 카드 순서대로 좌표가 있는 위치에 1부터 번호를 매긴다.
 * 카드 순서를 바꾸면 지도 핀 번호도 따라 바뀐다.
 */
export function numberStops(items: ItineraryItem[]): { points: RoutePoint[]; numbers: Map<string, number> } {
  const points: RoutePoint[] = [];
  const numbers = new Map<string, number>();
  items.forEach((item) =>
    item.stops.forEach((stop, stopIndex) => {
      if (stop.lat === undefined || stop.lng === undefined) return;
      const order = points.length + 1;
      numbers.set(stopKey(item.id, stopIndex), order);
      points.push({ order, kind: stop.kind, label: stop.label, lat: stop.lat, lng: stop.lng });
    }),
  );
  return { points, numbers };
}

/** 그날 위치가 없을 때 지도에 보여줄 여행 도시들 */
export function cityPoints(trip: Trip): RoutePoint[] {
  return trip.destinations
    .map((dest) => findCityByCode(dest.city_code))
    .filter((city) => city !== undefined)
    .map((city, index) => ({ order: index + 1, kind: "city", label: city.city, lat: city.lat, lng: city.lng }));
}
