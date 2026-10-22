import { AIRPORTS } from "../onboarding/airports";
import { findCityByName } from "../onboarding/cities";
import type { Destination, FlightBooking, FlightSegmentData, HotelBooking } from "../types/api";

/**
 * 예약 정보로 여행 만들기: 확인한 항공·숙소 예약에서 여행 기간과 여행지 기본값을 정한다(최종 확인에서 고칠 수 있다).
 * 외부 API를 쓰지 않고 앱에 들어 있는 공항·도시 목록만 쓴다.
 */

/** 같은 공항에서 이 시간 안에 다음 구간이 출발하면 환승으로 본다(여행지로 넣지 않는다). */
export const TRANSFER_HOURS = 24;

const moment = (day: string | null, time: string | null) => (day ? new Date(`${day}T${time ?? "00:00"}:00`).getTime() : NaN);

/** 예약 건의 구간을 출발 순서대로 펼친다. */
export function segmentsOf(flight: FlightBooking): FlightSegmentData[] {
  return flight.itineraries
    .flatMap((itinerary) => itinerary.segments)
    .slice()
    .sort((a, b) => moment(a.departure_date, a.departure_time) - moment(b.departure_date, b.departure_time));
}

/** 공항 코드 -> 앱의 여행지(도시). 공항 목록에 없거나 도시를 찾지 못하면 null */
export function cityOfAirport(code: string | null): Destination | null {
  const airport = code ? AIRPORTS.find((item) => item.code === code) : undefined;
  const city = airport ? findCityByName(airport.city) : undefined;
  return city ? { city: city.city, city_code: city.city_code } : null;
}

/**
 * 여행지 기본값: 구간 도착 공항의 도시를 방문 순서대로. 출발지(첫 출발 공항의 도시)와 환승지(24시간 안에 같은 공항에서
 * 다음 구간이 출발)는 뺀다. 공항 목록에 없는 공항은 건너뛴다(사용자가 직접 추가).
 */
export function suggestDestinations(flight: FlightBooking): { destinations: Destination[]; unknownAirports: string[] } {
  const segments = segmentsOf(flight);
  const origin = cityOfAirport(segments[0]?.departure_airport_code ?? null);
  const destinations: Destination[] = [];
  const unknownAirports: string[] = [];
  segments.forEach((segment, index) => {
    const next = segments[index + 1];
    const landed = moment(segment.arrival_date ?? segment.departure_date, segment.arrival_time ?? segment.departure_time);
    const transfer =
      next &&
      next.departure_airport_code === segment.arrival_airport_code &&
      moment(next.departure_date, next.departure_time) - landed < TRANSFER_HOURS * 3600 * 1000;
    if (transfer || !segment.arrival_airport_code) return;
    const city = cityOfAirport(segment.arrival_airport_code);
    if (!city) {
      if (!unknownAirports.includes(segment.arrival_airport_code)) unknownAirports.push(segment.arrival_airport_code);
      return;
    }
    if (origin && city.city_code === origin.city_code) return;
    if (!destinations.some((item) => item.city_code === city.city_code)) destinations.push(city);
  });
  return { destinations, unknownAirports };
}

/** 여행 기간 기본값: 첫 구간 출발일 ~ 마지막 구간 도착일과 마지막 숙소 체크아웃 중 늦은 날 */
export function suggestDates(flight: FlightBooking, hotels: HotelBooking | null): { start: string; end: string } {
  const segments = segmentsOf(flight);
  const start = segments[0]?.departure_date ?? "";
  const ends = [
    ...segments.map((segment) => segment.arrival_date ?? segment.departure_date ?? ""),
    ...(hotels?.stays ?? []).map((stay) => stay.check_out_date ?? ""),
  ].filter(Boolean);
  const end = ends.reduce((latest, day) => (day > latest ? day : latest), start);
  return { start, end };
}

/** 숙소의 여행지 추정: 여행지가 하나면 그곳, 아니면 주소·이름에 도시 이름이 들어간 여행지(없으면 빈 값). */
export function guessHotelCity(
  stay: { name: string | null; address: string | null },
  destinations: Destination[],
): string {
  if (destinations.length === 1) return destinations[0].city_code;
  const text = `${stay.address ?? ""} ${stay.name ?? ""}`;
  return destinations.find((destination) => destination.city && text.includes(destination.city))?.city_code ?? "";
}
