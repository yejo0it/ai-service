/**
 * 여행지 자동완성용 도시 목록.
 * city_code는 IATA 도시 코드(공항 코드가 아니라 도시 단위 코드)를 쓴다.
 * 예) 도쿄=TYO(하네다 HND + 나리타 NRT), 서울=SEL(김포 GMP + 인천 ICN)
 */

import type { Destination } from "../types/api";

/** 자동완성 후보 도시. 여행지(Destination)와 같은 모양이다. */
export type CityOption = Destination;

export const CITIES: CityOption[] = [
  // 한국
  { city: "서울", city_code: "SEL" },
  { city: "부산", city_code: "PUS" },
  { city: "제주", city_code: "CJU" },
  // 일본
  { city: "도쿄", city_code: "TYO" },
  { city: "오사카", city_code: "OSA" },
  { city: "나고야", city_code: "NGO" },
  { city: "후쿠오카", city_code: "FUK" },
  { city: "삿포로", city_code: "SPK" },
  { city: "오키나와", city_code: "OKA" },
  { city: "센다이", city_code: "SDJ" },
  { city: "히로시마", city_code: "HIJ" },
  { city: "가고시마", city_code: "KOJ" },
  { city: "다카마쓰", city_code: "TAK" },
  // 중화권
  { city: "베이징", city_code: "BJS" },
  { city: "상하이", city_code: "SHA" },
  { city: "광저우", city_code: "CAN" },
  { city: "칭다오", city_code: "TAO" },
  { city: "시안", city_code: "SIA" },
  { city: "홍콩", city_code: "HKG" },
  { city: "마카오", city_code: "MFM" },
  { city: "타이베이", city_code: "TPE" },
  { city: "가오슝", city_code: "KHH" },
  // 동남아시아
  { city: "방콕", city_code: "BKK" },
  { city: "치앙마이", city_code: "CNX" },
  { city: "푸껫", city_code: "HKT" },
  { city: "싱가포르", city_code: "SIN" },
  { city: "쿠알라룸푸르", city_code: "KUL" },
  { city: "코타키나발루", city_code: "BKI" },
  { city: "하노이", city_code: "HAN" },
  { city: "호치민", city_code: "SGN" },
  { city: "다낭", city_code: "DAD" },
  { city: "나트랑", city_code: "CXR" },
  { city: "푸꾸옥", city_code: "PQC" },
  { city: "마닐라", city_code: "MNL" },
  { city: "세부", city_code: "CEB" },
  { city: "보라카이", city_code: "MPH" },
  { city: "발리", city_code: "DPS" },
  { city: "자카르타", city_code: "JKT" },
  { city: "프놈펜", city_code: "PNH" },
  { city: "시엠립", city_code: "REP" },
  { city: "비엔티안", city_code: "VTE" },
  { city: "양곤", city_code: "RGN" },
  // 남아시아 · 중앙아시아
  { city: "델리", city_code: "DEL" },
  { city: "뭄바이", city_code: "BOM" },
  { city: "카트만두", city_code: "KTM" },
  { city: "콜롬보", city_code: "CMB" },
  { city: "몰디브", city_code: "MLE" },
  { city: "울란바토르", city_code: "ULN" },
  { city: "알마티", city_code: "ALA" },
  { city: "타슈켄트", city_code: "TAS" },
  // 중동
  { city: "두바이", city_code: "DXB" },
  { city: "아부다비", city_code: "AUH" },
  { city: "도하", city_code: "DOH" },
  { city: "이스탄불", city_code: "IST" },
  { city: "텔아비브", city_code: "TLV" },
  // 유럽
  { city: "파리", city_code: "PAR" },
  { city: "런던", city_code: "LON" },
  { city: "로마", city_code: "ROM" },
  { city: "밀라노", city_code: "MIL" },
  { city: "베네치아", city_code: "VCE" },
  { city: "피렌체", city_code: "FLR" },
  { city: "나폴리", city_code: "NAP" },
  { city: "바르셀로나", city_code: "BCN" },
  { city: "마드리드", city_code: "MAD" },
  { city: "리스본", city_code: "LIS" },
  { city: "포르투", city_code: "OPO" },
  { city: "암스테르담", city_code: "AMS" },
  { city: "브뤼셀", city_code: "BRU" },
  { city: "베를린", city_code: "BER" },
  { city: "뮌헨", city_code: "MUC" },
  { city: "프랑크푸르트", city_code: "FRA" },
  { city: "프라하", city_code: "PRG" },
  { city: "빈", city_code: "VIE" },
  { city: "부다페스트", city_code: "BUD" },
  { city: "취리히", city_code: "ZRH" },
  { city: "제네바", city_code: "GVA" },
  { city: "코펜하겐", city_code: "CPH" },
  { city: "스톡홀름", city_code: "STO" },
  { city: "오슬로", city_code: "OSL" },
  { city: "헬싱키", city_code: "HEL" },
  { city: "레이캬비크", city_code: "REK" },
  { city: "더블린", city_code: "DUB" },
  { city: "에든버러", city_code: "EDI" },
  { city: "아테네", city_code: "ATH" },
  { city: "바르샤바", city_code: "WAW" },
  { city: "자그레브", city_code: "ZAG" },
  { city: "두브로브니크", city_code: "DBV" },
  { city: "모스크바", city_code: "MOW" },
  // 북미
  { city: "뉴욕", city_code: "NYC" },
  { city: "로스앤젤레스", city_code: "LAX" },
  { city: "샌프란시스코", city_code: "SFO" },
  { city: "라스베이거스", city_code: "LAS" },
  { city: "시애틀", city_code: "SEA" },
  { city: "시카고", city_code: "CHI" },
  { city: "워싱턴", city_code: "WAS" },
  { city: "보스턴", city_code: "BOS" },
  { city: "마이애미", city_code: "MIA" },
  { city: "올랜도", city_code: "ORL" },
  { city: "호놀룰루", city_code: "HNL" },
  { city: "밴쿠버", city_code: "YVR" },
  { city: "토론토", city_code: "YTO" },
  // 중남미
  { city: "멕시코시티", city_code: "MEX" },
  { city: "칸쿤", city_code: "CUN" },
  { city: "상파울루", city_code: "SAO" },
  { city: "리우데자네이루", city_code: "RIO" },
  { city: "부에노스아이레스", city_code: "BUE" },
  { city: "리마", city_code: "LIM" },
  // 오세아니아 · 태평양
  { city: "시드니", city_code: "SYD" },
  { city: "멜버른", city_code: "MEL" },
  { city: "브리즈번", city_code: "BNE" },
  { city: "골드코스트", city_code: "OOL" },
  { city: "케언스", city_code: "CNS" },
  { city: "오클랜드", city_code: "AKL" },
  { city: "퀸스타운", city_code: "ZQN" },
  { city: "괌", city_code: "GUM" },
  { city: "사이판", city_code: "SPN" },
  { city: "나디", city_code: "NAN" },
  // 아프리카
  { city: "카이로", city_code: "CAI" },
  { city: "케이프타운", city_code: "CPT" },
  { city: "요하네스버그", city_code: "JNB" },
  { city: "나이로비", city_code: "NBO" },
  { city: "마라케시", city_code: "RAK" },
];

/** 입력한 도시명과 정확히 일치하는 도시(코드 자동 채움용). */
export function findCityByName(name: string): CityOption | undefined {
  const trimmed = name.trim();
  return CITIES.find((city) => city.city === trimmed);
}

/**
 * 입력어로 도시를 검색한다. 도시명과 도시코드 양쪽으로 찾으며,
 * 앞글자가 일치하는 항목을 먼저 보여준다. ('도' -> 도쿄 TYO, 도하 DOH)
 */
export function searchCities(query: string, limit = 6): CityOption[] {
  const keyword = query.trim();
  if (!keyword) return [];

  const upper = keyword.toUpperCase();
  const prefix: CityOption[] = [];
  const partial: CityOption[] = [];

  for (const city of CITIES) {
    if (city.city.startsWith(keyword) || city.city_code.startsWith(upper)) {
      prefix.push(city);
    } else if (city.city.includes(keyword)) {
      partial.push(city);
    }
  }
  return [...prefix, ...partial].slice(0, limit);
}
