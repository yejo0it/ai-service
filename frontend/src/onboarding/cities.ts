/**
 * 여행지 자동완성용 도시 목록.
 * city_code는 IATA 도시 코드(공항 코드가 아니라 도시 단위 코드)를 쓴다.
 * 예) 도쿄=TYO(하네다 HND + 나리타 NRT), 서울=SEL(김포 GMP + 인천 ICN)
 */

import type { Destination } from "../types/api";

/** 자동완성 후보 도시. 여행지(Destination) + 도시 중심 좌표(여행 상세 지도용). */
export interface CityOption extends Destination {
  lat: number;
  lng: number;
}

export const CITIES: CityOption[] = [
  // 한국
  { city: "서울", city_code: "SEL", lat: 37.5665, lng: 126.978 },
  { city: "부산", city_code: "PUS", lat: 35.1796, lng: 129.0756 },
  { city: "제주", city_code: "CJU", lat: 33.4996, lng: 126.5312 },
  // 일본
  { city: "도쿄", city_code: "TYO", lat: 35.6812, lng: 139.7671 },
  { city: "오사카", city_code: "OSA", lat: 34.6937, lng: 135.5023 },
  { city: "나고야", city_code: "NGO", lat: 35.1815, lng: 136.9066 },
  { city: "후쿠오카", city_code: "FUK", lat: 33.5902, lng: 130.4017 },
  { city: "삿포로", city_code: "SPK", lat: 43.0618, lng: 141.3545 },
  { city: "오키나와", city_code: "OKA", lat: 26.2124, lng: 127.6809 },
  { city: "센다이", city_code: "SDJ", lat: 38.2682, lng: 140.8694 },
  { city: "히로시마", city_code: "HIJ", lat: 34.3853, lng: 132.4553 },
  { city: "가고시마", city_code: "KOJ", lat: 31.5966, lng: 130.5571 },
  { city: "다카마쓰", city_code: "TAK", lat: 34.3428, lng: 134.0466 },
  // 중화권
  { city: "베이징", city_code: "BJS", lat: 39.9042, lng: 116.4074 },
  { city: "상하이", city_code: "SHA", lat: 31.2304, lng: 121.4737 },
  { city: "광저우", city_code: "CAN", lat: 23.1291, lng: 113.2644 },
  { city: "칭다오", city_code: "TAO", lat: 36.0671, lng: 120.3826 },
  { city: "시안", city_code: "SIA", lat: 34.3416, lng: 108.9398 },
  { city: "홍콩", city_code: "HKG", lat: 22.3193, lng: 114.1694 },
  { city: "마카오", city_code: "MFM", lat: 22.1987, lng: 113.5439 },
  { city: "타이베이", city_code: "TPE", lat: 25.033, lng: 121.5654 },
  { city: "가오슝", city_code: "KHH", lat: 22.6273, lng: 120.3014 },
  // 동남아시아
  { city: "방콕", city_code: "BKK", lat: 13.7563, lng: 100.5018 },
  { city: "치앙마이", city_code: "CNX", lat: 18.7883, lng: 98.9853 },
  { city: "푸껫", city_code: "HKT", lat: 7.8804, lng: 98.3923 },
  { city: "싱가포르", city_code: "SIN", lat: 1.3521, lng: 103.8198 },
  { city: "쿠알라룸푸르", city_code: "KUL", lat: 3.139, lng: 101.6869 },
  { city: "코타키나발루", city_code: "BKI", lat: 5.9804, lng: 116.0735 },
  { city: "하노이", city_code: "HAN", lat: 21.0278, lng: 105.8342 },
  { city: "호치민", city_code: "SGN", lat: 10.8231, lng: 106.6297 },
  { city: "다낭", city_code: "DAD", lat: 16.0544, lng: 108.2022 },
  { city: "나트랑", city_code: "CXR", lat: 12.2388, lng: 109.1967 },
  { city: "푸꾸옥", city_code: "PQC", lat: 10.2899, lng: 103.984 },
  { city: "마닐라", city_code: "MNL", lat: 14.5995, lng: 120.9842 },
  { city: "세부", city_code: "CEB", lat: 10.3157, lng: 123.8854 },
  { city: "보라카이", city_code: "MPH", lat: 11.9674, lng: 121.9248 },
  { city: "발리", city_code: "DPS", lat: -8.65, lng: 115.2167 },
  { city: "자카르타", city_code: "JKT", lat: -6.2088, lng: 106.8456 },
  { city: "프놈펜", city_code: "PNH", lat: 11.5564, lng: 104.9282 },
  { city: "시엠립", city_code: "REP", lat: 13.3671, lng: 103.8448 },
  { city: "비엔티안", city_code: "VTE", lat: 17.9757, lng: 102.6331 },
  { city: "양곤", city_code: "RGN", lat: 16.8409, lng: 96.1735 },
  // 남아시아 · 중앙아시아
  { city: "델리", city_code: "DEL", lat: 28.6139, lng: 77.209 },
  { city: "뭄바이", city_code: "BOM", lat: 19.076, lng: 72.8777 },
  { city: "카트만두", city_code: "KTM", lat: 27.7172, lng: 85.324 },
  { city: "콜롬보", city_code: "CMB", lat: 6.9271, lng: 79.8612 },
  { city: "몰디브", city_code: "MLE", lat: 4.1755, lng: 73.5093 },
  { city: "울란바토르", city_code: "ULN", lat: 47.8864, lng: 106.9057 },
  { city: "알마티", city_code: "ALA", lat: 43.222, lng: 76.8512 },
  { city: "타슈켄트", city_code: "TAS", lat: 41.2995, lng: 69.2401 },
  // 중동
  { city: "두바이", city_code: "DXB", lat: 25.2048, lng: 55.2708 },
  { city: "아부다비", city_code: "AUH", lat: 24.4539, lng: 54.3773 },
  { city: "도하", city_code: "DOH", lat: 25.2854, lng: 51.531 },
  { city: "이스탄불", city_code: "IST", lat: 41.0082, lng: 28.9784 },
  { city: "텔아비브", city_code: "TLV", lat: 32.0853, lng: 34.7818 },
  // 유럽
  { city: "파리", city_code: "PAR", lat: 48.8566, lng: 2.3522 },
  { city: "런던", city_code: "LON", lat: 51.5074, lng: -0.1278 },
  { city: "로마", city_code: "ROM", lat: 41.9028, lng: 12.4964 },
  { city: "밀라노", city_code: "MIL", lat: 45.4642, lng: 9.19 },
  { city: "베네치아", city_code: "VCE", lat: 45.4408, lng: 12.3155 },
  { city: "피렌체", city_code: "FLR", lat: 43.7696, lng: 11.2558 },
  { city: "나폴리", city_code: "NAP", lat: 40.8518, lng: 14.2681 },
  { city: "바르셀로나", city_code: "BCN", lat: 41.3874, lng: 2.1686 },
  { city: "마드리드", city_code: "MAD", lat: 40.4168, lng: -3.7038 },
  { city: "리스본", city_code: "LIS", lat: 38.7223, lng: -9.1393 },
  { city: "포르투", city_code: "OPO", lat: 41.1579, lng: -8.6291 },
  { city: "암스테르담", city_code: "AMS", lat: 52.3676, lng: 4.9041 },
  { city: "브뤼셀", city_code: "BRU", lat: 50.8503, lng: 4.3517 },
  { city: "베를린", city_code: "BER", lat: 52.52, lng: 13.405 },
  { city: "뮌헨", city_code: "MUC", lat: 48.1351, lng: 11.582 },
  { city: "프랑크푸르트", city_code: "FRA", lat: 50.1109, lng: 8.6821 },
  { city: "프라하", city_code: "PRG", lat: 50.0755, lng: 14.4378 },
  { city: "빈", city_code: "VIE", lat: 48.2082, lng: 16.3738 },
  { city: "부다페스트", city_code: "BUD", lat: 47.4979, lng: 19.0402 },
  { city: "취리히", city_code: "ZRH", lat: 47.3769, lng: 8.5417 },
  { city: "제네바", city_code: "GVA", lat: 46.2044, lng: 6.1432 },
  { city: "코펜하겐", city_code: "CPH", lat: 55.6761, lng: 12.5683 },
  { city: "스톡홀름", city_code: "STO", lat: 59.3293, lng: 18.0686 },
  { city: "오슬로", city_code: "OSL", lat: 59.9139, lng: 10.7522 },
  { city: "헬싱키", city_code: "HEL", lat: 60.1699, lng: 24.9384 },
  { city: "레이캬비크", city_code: "REK", lat: 64.1466, lng: -21.9426 },
  { city: "더블린", city_code: "DUB", lat: 53.3498, lng: -6.2603 },
  { city: "에든버러", city_code: "EDI", lat: 55.9533, lng: -3.1883 },
  { city: "아테네", city_code: "ATH", lat: 37.9838, lng: 23.7275 },
  { city: "바르샤바", city_code: "WAW", lat: 52.2297, lng: 21.0122 },
  { city: "자그레브", city_code: "ZAG", lat: 45.815, lng: 15.9819 },
  { city: "두브로브니크", city_code: "DBV", lat: 42.6507, lng: 18.0944 },
  { city: "모스크바", city_code: "MOW", lat: 55.7558, lng: 37.6173 },
  // 북미
  { city: "뉴욕", city_code: "NYC", lat: 40.7128, lng: -74.006 },
  { city: "로스앤젤레스", city_code: "LAX", lat: 34.0522, lng: -118.2437 },
  { city: "샌프란시스코", city_code: "SFO", lat: 37.7749, lng: -122.4194 },
  { city: "라스베이거스", city_code: "LAS", lat: 36.1699, lng: -115.1398 },
  { city: "시애틀", city_code: "SEA", lat: 47.6062, lng: -122.3321 },
  { city: "시카고", city_code: "CHI", lat: 41.8781, lng: -87.6298 },
  { city: "워싱턴", city_code: "WAS", lat: 38.9072, lng: -77.0369 },
  { city: "보스턴", city_code: "BOS", lat: 42.3601, lng: -71.0589 },
  { city: "마이애미", city_code: "MIA", lat: 25.7617, lng: -80.1918 },
  { city: "올랜도", city_code: "ORL", lat: 28.5383, lng: -81.3792 },
  { city: "호놀룰루", city_code: "HNL", lat: 21.3069, lng: -157.8583 },
  { city: "밴쿠버", city_code: "YVR", lat: 49.2827, lng: -123.1207 },
  { city: "토론토", city_code: "YTO", lat: 43.6532, lng: -79.3832 },
  // 중남미
  { city: "멕시코시티", city_code: "MEX", lat: 19.4326, lng: -99.1332 },
  { city: "칸쿤", city_code: "CUN", lat: 21.1619, lng: -86.8515 },
  { city: "상파울루", city_code: "SAO", lat: -23.5505, lng: -46.6333 },
  { city: "리우데자네이루", city_code: "RIO", lat: -22.9068, lng: -43.1729 },
  { city: "부에노스아이레스", city_code: "BUE", lat: -34.6037, lng: -58.3816 },
  { city: "리마", city_code: "LIM", lat: -12.0464, lng: -77.0428 },
  // 오세아니아 · 태평양
  { city: "시드니", city_code: "SYD", lat: -33.8688, lng: 151.2093 },
  { city: "멜버른", city_code: "MEL", lat: -37.8136, lng: 144.9631 },
  { city: "브리즈번", city_code: "BNE", lat: -27.4698, lng: 153.0251 },
  { city: "골드코스트", city_code: "OOL", lat: -28.0167, lng: 153.4 },
  { city: "케언스", city_code: "CNS", lat: -16.9186, lng: 145.7781 },
  { city: "오클랜드", city_code: "AKL", lat: -36.8485, lng: 174.7633 },
  { city: "퀸스타운", city_code: "ZQN", lat: -45.0312, lng: 168.6626 },
  { city: "괌", city_code: "GUM", lat: 13.4443, lng: 144.7937 },
  { city: "사이판", city_code: "SPN", lat: 15.185, lng: 145.7467 },
  { city: "나디", city_code: "NAN", lat: -17.7765, lng: 177.4356 },
  // 아프리카
  { city: "카이로", city_code: "CAI", lat: 30.0444, lng: 31.2357 },
  { city: "케이프타운", city_code: "CPT", lat: -33.9249, lng: 18.4241 },
  { city: "요하네스버그", city_code: "JNB", lat: -26.2041, lng: 28.0473 },
  { city: "나이로비", city_code: "NBO", lat: -1.2921, lng: 36.8219 },
  { city: "마라케시", city_code: "RAK", lat: 31.6295, lng: -7.9811 },
];

/** 입력한 도시명과 정확히 일치하는 도시(코드 자동 채움용). */
/** 도시코드로 도시 찾기 (지도 좌표용) */
export const findCityByCode = (code: string) => CITIES.find((city) => city.city_code === code);

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
