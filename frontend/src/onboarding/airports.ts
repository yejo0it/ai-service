/**
 * 출국·귀국 공항 자동완성 검색. 국내 출발 공항과 여행지 도시의 주요 공항을 담는다.
 * 공항 목록은 src/data/airports.json에 있다(이 목록이 원본, 공항을 추가할 때는 그 파일을 고친다).
 * 목록에 있는 공항만 선택할 수 있다(직접 입력 불가).
 */

import airports from "../data/airports.json";

export interface AirportOption {
  /** 목록 안의 고유값 (터미널이 나뉘는 공항은 코드-터미널) */
  id: string;
  /** IATA 공항 코드 */
  code: string;
  name: string;
  /** 검색용 도시명 */
  city: string;
  /** 목록 묶음 (한국, 일본 ...) */
  region: string;
  /** 공항 위치(여행 상세 지도 핀용, 공항 부지 기준 근삿값) */
  lat: number;
  lng: number;
}

export const AIRPORTS: AirportOption[] = airports;

/** 저장된 공항(code·name)으로 목록의 공항 찾기. 같은 코드의 터미널은 이름으로 구분한다. */
export const findAirport = (code: string, name: string) =>
  AIRPORTS.find((item) => item.code === code && item.name === name) ??
  AIRPORTS.find((item) => item.code === code);

/** 입력한 이름과 정확히 일치하는 공항 (포커스를 떠날 때 확정용) */
export function findAirportByName(name: string): AirportOption | undefined {
  const trimmed = name.trim();
  return AIRPORTS.find((item) => item.name === trimmed);
}

/**
 * 공항명 · 도시명 · IATA 코드로 찾는다. 앞글자가 일치하는 항목을 먼저 보여준다.
 * ('인천' -> 인천공항 1·2터미널 / '도쿄' -> 나리타·하네다 / 'NRT' -> 나리타공항)
 */
export function searchAirports(query: string, limit = 6): AirportOption[] {
  const keyword = query.trim();
  if (!keyword) return [];

  const upper = keyword.toUpperCase();
  const prefix: AirportOption[] = [];
  const partial: AirportOption[] = [];
  for (const item of AIRPORTS) {
    if (item.name.startsWith(keyword) || item.city.startsWith(keyword) || item.code.startsWith(upper)) {
      prefix.push(item);
    } else if (item.name.includes(keyword) || item.city.includes(keyword)) {
      partial.push(item);
    }
  }
  return [...prefix, ...partial].slice(0, limit);
}
