/**
 * 여행지 자동완성용 도시 검색.
 * 도시 목록(CITIES)은 backend/data/cities.json에서 생성한 citiesData.ts에 있다(직접 수정하지 않는다).
 * city_code는 서비스 자체 도시 id다(예: 도쿄=tokyo, 하코네=hakone). IATA 도시 코드가 없는 소도시도 있다.
 */

import type { Destination } from "../types/api";
import { CITIES } from "./citiesData";

export { CITIES };

/** 자동완성 후보 도시. 여행지(Destination) + 도시 중심 좌표(여행 상세 지도용) + 검색어. */
export interface CityOption extends Destination {
  /** IATA 도시 코드 (없으면 null). 검색과 예전 데이터 호환에만 쓴다. */
  iata: string | null;
  /** 소속 도·현 (예: 가나가와현). 자동완성 안내와 검색에 쓴다. 모르면 빈 문자열. */
  admin1: string;
  /** 영문명 등 검색어 */
  aliases: string[];
  lat: number;
  lng: number;
}

/**
 * 도시 키로 도시 찾기 (지도 좌표용).
 * 예전에 저장된 IATA 도시 코드(예: "TYO")로 찾아도 같은 도시를 돌려준다.
 */
export const findCityByCode = (code: string) =>
  CITIES.find((city) => city.city_code === code) ??
  (code ? CITIES.find((city) => city.iata === code.toUpperCase()) : undefined);

/** 입력한 도시명과 정확히 일치하는 도시(도시 키 자동 채움용). */
export function findCityByName(name: string): CityOption | undefined {
  const trimmed = name.trim();
  return CITIES.find((city) => city.city === trimmed);
}

/**
 * 입력어로 도시를 검색한다. 한글 도시명 · 영문명 · IATA 도시 코드로 찾고, 이름이 정확히 같은 도시,
 * 앞글자가 일치하는 도시 순으로 보여준다.
 * 소속 도·현으로도 찾는다(도시 이름으로 찾은 결과 뒤에 붙인다).
 * 예) '도' -> 도쿄, 도하 / 'hako' -> 하코네 / 'TYO' -> 도쿄 / '가나가와' -> 요코하마, 하코네
 */
export function searchCities(query: string, limit = 6): CityOption[] {
  const keyword = query.trim();
  if (!keyword) return [];

  const lower = keyword.toLowerCase();
  const upper = keyword.toUpperCase();
  const exact: CityOption[] = [];
  const prefix: CityOption[] = [];
  const partial: CityOption[] = [];
  const byRegion: CityOption[] = [];

  for (const city of CITIES) {
    const aliases = city.aliases.map((alias) => alias.toLowerCase());
    if (city.city === keyword) {
      exact.push(city);
    } else if (
      city.city.startsWith(keyword) ||
      aliases.some((alias) => alias.startsWith(lower)) ||
      (city.iata !== null && city.iata.startsWith(upper))
    ) {
      prefix.push(city);
    } else if (city.city.includes(keyword) || aliases.some((alias) => alias.includes(lower))) {
      partial.push(city);
    } else if (keyword.length >= 2 && city.admin1.startsWith(keyword)) {
      byRegion.push(city);
    }
  }
  return [...exact, ...prefix, ...partial, ...byRegion].slice(0, limit);
}
