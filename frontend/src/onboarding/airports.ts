/**
 * 출국·귀국 공항 자동완성 목록. 국내 출발 공항과 여행지(cities.ts) 도시의 주요 공항을 담는다.
 * 목록에 있는 공항만 선택할 수 있다(직접 입력 불가).
 *
 * id: 목록 안의 고유값 (터미널이 나뉘는 공항은 코드-터미널)
 * code: IATA 공항 코드 / city: 검색용 도시명
 */
export interface AirportOption {
  id: string;
  code: string;
  name: string;
  city: string;
}

const airport = (code: string, name: string, city: string, id = code): AirportOption => ({
  id,
  code,
  name,
  city,
});

export const AIRPORTS: AirportOption[] = [
  // 한국
  airport("ICN", "인천공항 1터미널", "인천", "ICN-T1"),
  airport("ICN", "인천공항 2터미널", "인천", "ICN-T2"),
  airport("GMP", "김포공항", "서울"),
  airport("PUS", "김해공항", "부산"),
  airport("CJU", "제주공항", "제주"),
  airport("TAE", "대구공항", "대구"),
  airport("CJJ", "청주공항", "청주"),
  airport("MWX", "무안공항", "무안"),
  airport("YNY", "양양공항", "양양"),
  // 일본
  airport("NRT", "나리타공항", "도쿄"),
  airport("HND", "하네다공항", "도쿄"),
  airport("KIX", "간사이공항", "오사카"),
  airport("ITM", "이타미공항", "오사카"),
  airport("NGO", "주부공항", "나고야"),
  airport("FUK", "후쿠오카공항", "후쿠오카"),
  airport("CTS", "신치토세공항", "삿포로"),
  airport("OKA", "나하공항", "오키나와"),
  airport("SDJ", "센다이공항", "센다이"),
  airport("HIJ", "히로시마공항", "히로시마"),
  airport("KOJ", "가고시마공항", "가고시마"),
  airport("TAK", "다카마쓰공항", "다카마쓰"),
  // 중화권
  airport("PEK", "베이징 서우두공항", "베이징"),
  airport("PKX", "베이징 다싱공항", "베이징"),
  airport("PVG", "상하이 푸둥공항", "상하이"),
  airport("SHA", "상하이 훙차오공항", "상하이"),
  airport("CAN", "광저우 바이윈공항", "광저우"),
  airport("TAO", "칭다오 자오둥공항", "칭다오"),
  airport("XIY", "시안 셴양공항", "시안"),
  airport("HKG", "홍콩공항", "홍콩"),
  airport("MFM", "마카오공항", "마카오"),
  airport("TPE", "타오위안공항", "타이베이"),
  airport("TSA", "쑹산공항", "타이베이"),
  airport("KHH", "가오슝공항", "가오슝"),
  // 동남아시아
  airport("BKK", "수완나품공항", "방콕"),
  airport("DMK", "돈므앙공항", "방콕"),
  airport("CNX", "치앙마이공항", "치앙마이"),
  airport("HKT", "푸껫공항", "푸껫"),
  airport("SIN", "창이공항", "싱가포르"),
  airport("KUL", "쿠알라룸푸르공항", "쿠알라룸푸르"),
  airport("BKI", "코타키나발루공항", "코타키나발루"),
  airport("HAN", "노이바이공항", "하노이"),
  airport("SGN", "떤선녓공항", "호찌민"),
  airport("DAD", "다낭공항", "다낭"),
  airport("CXR", "깜라인공항", "나트랑"),
  airport("PQC", "푸꾸옥공항", "푸꾸옥"),
  airport("MNL", "니노이아키노공항", "마닐라"),
  airport("CEB", "막탄세부공항", "세부"),
  airport("MPH", "카티클란공항", "보라카이"),
  airport("DPS", "응우라라이공항", "발리"),
  airport("CGK", "수카르노하타공항", "자카르타"),
  airport("KTI", "테초공항", "프놈펜"),
  airport("SAI", "시엠레아프앙코르공항", "시엠레아프"),
  airport("VTE", "왓따이공항", "비엔티안"),
  airport("RGN", "양곤공항", "양곤"),
  // 남아시아 · 중앙아시아
  airport("DEL", "델리공항", "델리"),
  airport("BOM", "뭄바이공항", "뭄바이"),
  airport("KTM", "카트만두공항", "카트만두"),
  airport("CMB", "콜롬보공항", "콜롬보"),
  airport("MLE", "말레공항", "몰디브"),
  airport("UBN", "칭기스칸공항", "울란바토르"),
  airport("ALA", "알마티공항", "알마티"),
  airport("TAS", "타슈켄트공항", "타슈켄트"),
  // 중동
  airport("DXB", "두바이공항", "두바이"),
  airport("AUH", "아부다비공항", "아부다비"),
  airport("DOH", "하마드공항", "도하"),
  airport("IST", "이스탄불공항", "이스탄불"),
  airport("TLV", "벤구리온공항", "텔아비브"),
  // 유럽
  airport("CDG", "샤를드골공항", "파리"),
  airport("LHR", "히스로공항", "런던"),
  airport("FCO", "피우미치노공항", "로마"),
  airport("MXP", "말펜사공항", "밀라노"),
  airport("VCE", "베네치아공항", "베네치아"),
  airport("FLR", "피렌체공항", "피렌체"),
  airport("NAP", "나폴리공항", "나폴리"),
  airport("BCN", "바르셀로나공항", "바르셀로나"),
  airport("MAD", "마드리드공항", "마드리드"),
  airport("LIS", "리스본공항", "리스본"),
  airport("OPO", "포르투공항", "포르투"),
  airport("AMS", "스히폴공항", "암스테르담"),
  airport("BRU", "브뤼셀공항", "브뤼셀"),
  airport("BER", "베를린공항", "베를린"),
  airport("MUC", "뮌헨공항", "뮌헨"),
  airport("FRA", "프랑크푸르트공항", "프랑크푸르트"),
  airport("PRG", "프라하공항", "프라하"),
  airport("VIE", "빈공항", "빈"),
  airport("BUD", "부다페스트공항", "부다페스트"),
  airport("ZRH", "취리히공항", "취리히"),
  airport("GVA", "제네바공항", "제네바"),
  airport("CPH", "코펜하겐공항", "코펜하겐"),
  airport("ARN", "알란다공항", "스톡홀름"),
  airport("OSL", "오슬로공항", "오슬로"),
  airport("HEL", "헬싱키공항", "헬싱키"),
  airport("KEF", "케플라비크공항", "레이캬비크"),
  airport("DUB", "더블린공항", "더블린"),
  airport("EDI", "에든버러공항", "에든버러"),
  airport("ATH", "아테네공항", "아테네"),
  airport("WAW", "바르샤바공항", "바르샤바"),
  airport("ZAG", "자그레브공항", "자그레브"),
  airport("DBV", "두브로브니크공항", "두브로브니크"),
  airport("SVO", "셰레메티예보공항", "모스크바"),
  // 북미
  airport("JFK", "존에프케네디공항", "뉴욕"),
  airport("EWR", "뉴어크공항", "뉴욕"),
  airport("LAX", "로스앤젤레스공항", "로스앤젤레스"),
  airport("SFO", "샌프란시스코공항", "샌프란시스코"),
  airport("LAS", "해리리드공항", "라스베이거스"),
  airport("SEA", "시애틀공항", "시애틀"),
  airport("ORD", "오헤어공항", "시카고"),
  airport("IAD", "덜레스공항", "워싱턴"),
  airport("BOS", "보스턴공항", "보스턴"),
  airport("MIA", "마이애미공항", "마이애미"),
  airport("MCO", "올랜도공항", "올랜도"),
  airport("HNL", "호놀룰루공항", "호놀룰루"),
  airport("YVR", "밴쿠버공항", "밴쿠버"),
  airport("YYZ", "피어슨공항", "토론토"),
  // 중남미
  airport("MEX", "멕시코시티공항", "멕시코시티"),
  airport("CUN", "칸쿤공항", "칸쿤"),
  airport("GRU", "과룰류스공항", "상파울루"),
  airport("GIG", "갈레앙공항", "리우데자네이루"),
  airport("EZE", "에세이사공항", "부에노스아이레스"),
  airport("LIM", "리마공항", "리마"),
  // 오세아니아 · 태평양
  airport("SYD", "시드니공항", "시드니"),
  airport("MEL", "멜버른공항", "멜버른"),
  airport("BNE", "브리즈번공항", "브리즈번"),
  airport("OOL", "골드코스트공항", "골드코스트"),
  airport("CNS", "케언스공항", "케언스"),
  airport("AKL", "오클랜드공항", "오클랜드"),
  airport("ZQN", "퀸스타운공항", "퀸스타운"),
  airport("GUM", "괌공항", "괌"),
  airport("SPN", "사이판공항", "사이판"),
  airport("NAN", "난디공항", "피지"),
  // 아프리카
  airport("CAI", "카이로공항", "카이로"),
  airport("CPT", "케이프타운공항", "케이프타운"),
  airport("JNB", "요하네스버그공항", "요하네스버그"),
  airport("NBO", "나이로비공항", "나이로비"),
  airport("RAK", "마라케시공항", "마라케시"),
];

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
