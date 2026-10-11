import { findAirport } from "../onboarding/airports";
import { findCityByCode } from "../onboarding/cities";
import type { Airport, Hotel, ItineraryCardInput, ItineraryItem, ItineraryStop, Trip } from "../types/api";
import { addDays, parseISODate, toISODate } from "../utils/date";

export type StopKind = ItineraryStop["kind"];

/** 핀 색 구분: 공항·숙소·여행지, 장소는 유형(관광지·식당·카페)별 */
export type PinKind = Exclude<StopKind, "place"> | "sight" | "restaurant" | "cafe";

/** 위치의 핀 색 구분. 장소는 카드 유형을 따른다. */
export const pinKind = (item: ItineraryItem, stop: ItineraryStop): PinKind => {
  if (stop.kind !== "place") return stop.kind;
  return item.kind === "restaurant" || item.kind === "cafe" ? item.kind : "sight";
};

/** 지도에 찍는 번호 핀 */
export interface RoutePoint {
  order: number;
  kind: PinKind;
  label: string;
  lat: number;
  lng: number;
}

const ORDINALS = ["첫째", "둘째", "셋째", "넷째", "다섯째", "여섯째", "일곱째", "여덟째", "아홉째", "열째"];

/** 0 -> "첫째 날", 10 -> "11일차" */
export const dayLabel = (index: number) => (ORDINALS[index] ? `${ORDINALS[index]} 날` : `${index + 1}일차`);

/** 여행 기간의 날짜들 ("YYYY-MM-DD") */
export function tripDates(trip: Trip): string[] {
  const dates: string[] = [];
  for (let date = parseISODate(trip.start_date); toISODate(date) <= trip.end_date; date = addDays(date, 1)) {
    dates.push(toISODate(date));
  }
  return dates;
}

const airportStop = (airport: Airport | null | undefined, caption: string): ItineraryStop => {
  const found = airport ? findAirport(airport.code, airport.name) : undefined;
  return { kind: "airport", caption, label: airport?.name ?? "공항 미지정", lat: found?.lat, lng: found?.lng };
};

const hotelCard = (hotel: Hotel, day: string, label: string, subtitle = ""): ItineraryCardInput => ({
  day,
  kind: "hotel",
  title: hotel.name,
  time: "",
  time_label: label,
  subtitle,
  stops: [{ kind: "hotel", caption: label, label: hotel.address || hotel.name, lat: hotel.latitude, lng: hotel.longitude }],
  phone: hotel.phone ?? "",
});

/**
 * 상세 화면을 처음 열 때 저장할 항공편·숙소 카드 (서버가 한 번만 저장한다).
 * - 가는 편: 출국일 / 오는 편: 귀국일
 * - 숙소: 체크인 날(체크인), 사이 날(숙박), 체크아웃 날(체크아웃)
 * 하루 안의 순서: 체크아웃 → 가는 편 → 숙박 → 체크인 → 오는 편
 */
export function initialCards(trip: Trip): ItineraryCardInput[] {
  const flight = trip.flight_info;
  const departureDate = flight?.departure_at?.slice(0, 10) || trip.start_date;
  const returnDate = flight?.return_arrival_at?.slice(0, 10) || trip.end_date;
  const hotels = [...trip.hotels].sort((a, b) => a.check_in.localeCompare(b.check_in));
  const cards: ItineraryCardInput[] = [];

  tripDates(trip).forEach((day) => {
    hotels
      .filter((hotel) => hotel.check_out === day && hotel.check_in !== day)
      .forEach((hotel) => cards.push(hotelCard(hotel, day, "체크아웃")));

    if (flight && day === departureDate) {
      cards.push({
        day,
        kind: "flight",
        title: `가는 편${flight.flight_number ? ` · ${flight.flight_number}` : ""}`,
        time: flight.departure_at?.slice(11, 16) ?? "",
        time_label: "출국",
        subtitle: "",
        stops: [airportStop(flight.departure_airport, "출발"), airportStop(flight.arrival_airport, "도착")],
      });
    }

    hotels
      .filter((hotel) => hotel.check_in < day && hotel.check_out !== null && day < hotel.check_out)
      .forEach((hotel) => cards.push(hotelCard(hotel, day, "숙박")));

    hotels
      .filter((hotel) => hotel.check_in === day)
      .forEach((hotel) => cards.push(hotelCard(hotel, day, "체크인", hotel.nights ? `${hotel.nights}박` : "")));

    if (flight && day === returnDate && (flight.return_flight_number || flight.return_arrival_at)) {
      cards.push({
        day,
        kind: "flight",
        title: `오는 편${flight.return_flight_number ? ` · ${flight.return_flight_number}` : ""}`,
        time: flight.return_arrival_at?.slice(11, 16) ?? "",
        time_label: "귀국",
        subtitle: "",
        stops: [
          airportStop(flight.return_departure_airport, "출발"),
          airportStop(flight.return_arrival_airport, "도착"),
        ],
      });
    }
  });
  return cards;
}

/** 카드 안 위치의 키 (번호 조회용) */
export const stopKey = (itemId: number, stopIndex: number) => `${itemId}:${stopIndex}`;

/** 출발지(한국) 쪽 공항: 가는 편의 출발 공항, 오는 편의 도착 공항. 지도에는 여행지 안의 이동만 그린다. */
const isHomeAirport = (item: ItineraryItem, stopIndex: number) =>
  item.kind === "flight" &&
  ((item.time_label === "출국" && stopIndex === 0) ||
    (item.time_label === "귀국" && stopIndex === item.stops.length - 1));

/**
 * 카드 순서대로 좌표가 있는 위치에 1부터 번호를 매긴다(출발지 쪽 공항은 빼고 현지 공항부터).
 * 카드 순서를 바꾸면 지도 핀 번호도 따라 바뀐다.
 */
export function numberStops(items: ItineraryItem[]): { points: RoutePoint[]; numbers: Map<string, number> } {
  const points: RoutePoint[] = [];
  const numbers = new Map<string, number>();
  items.forEach((item) =>
    item.stops.forEach((stop, stopIndex) => {
      if (stop.lat == null || stop.lng == null || isHomeAirport(item, stopIndex)) return;
      const order = points.length + 1;
      numbers.set(stopKey(item.id, stopIndex), order);
      points.push({ order, kind: pinKind(item, stop), label: stop.label, lat: stop.lat, lng: stop.lng });
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
