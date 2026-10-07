/**
 * 항공사 자동완성 검색.
 * 항공사 목록은 src/data/airlines.json에 있다. `scripts/generate_airlines.py`가 생성하므로 직접 수정하지 않는다.
 * 원본: backend/data/airlines.csv (영문명은 backend/data/airline_names_en.json에서 보완)
 */

import airlines from "../data/airlines.json";

export interface AirlineOption {
  /** IATA 항공사 코드 (편명 앞에 붙는 2자리) */
  code: string;
  /** 국문 항공사명 */
  name: string;
  /** 영문 항공사명 (주요 항공사만). 없으면 한글명과 코드로만 검색된다. */
  name_en?: string;
}

export const AIRLINES: AirlineOption[] = airlines;

/** CSV 표기는 '에어 서울'처럼 띄어쓰기가 섞여 있어, 비교 시 공백을 무시한다. */
const squash = (value: string) => value.replace(/\s+/g, "").toLowerCase();

/** 입력한 이름과 일치하는 항공사(코드 자동 채움용). 띄어쓰기는 무시한다. */
export function findAirlineByName(name: string): AirlineOption | undefined {
  const key = squash(name);
  if (!key) return undefined;
  return AIRLINES.find((airline) => squash(airline.name) === key);
}

/**
 * 입력어로 항공사를 검색한다. 국문명 · 영문명 · IATA 코드로 찾으며,
 * 코드가 정확히 맞거나 앞글자가 일치하는 항목을 먼저 보여준다.
 * ('대한' -> 대한항공 KE / 'KE' -> 대한항공 KE / 'korean' -> 대한항공 KE)
 */
export function searchAirlines(query: string, limit = 6): AirlineOption[] {
  const keyword = query.trim();
  if (!keyword) return [];

  const upper = keyword.toUpperCase();
  const key = squash(keyword);
  const exact: AirlineOption[] = [];
  const prefix: AirlineOption[] = [];
  const partial: AirlineOption[] = [];

  for (const airline of AIRLINES) {
    const name = squash(airline.name);
    const nameEn = squash(airline.name_en ?? "");
    if (airline.code === upper) {
      exact.push(airline);
    } else if (name.startsWith(key) || (nameEn && nameEn.startsWith(key))) {
      prefix.push(airline);
    } else if (name.includes(key) || (nameEn && nameEn.includes(key))) {
      partial.push(airline);
    }
  }
  return [...exact, ...prefix, ...partial].slice(0, limit);
}
