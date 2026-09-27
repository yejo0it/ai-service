"""backend/data/airlines.csv -> frontend/src/onboarding/airlines.js 생성.

항공사 목록은 자주 바뀌지 않으므로 프론트 상수 모듈로 내려 자동완성 반응 속도를 확보한다.
CSV가 원본이며, 목록을 고친 뒤 이 스크립트를 다시 돌리면 된다.

    python scripts/generate_airlines.py

표준 라이브러리만 사용하므로 Django 환경 없이 호스트에서 바로 실행할 수 있다.
"""

import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "backend" / "data" / "airlines.csv"
OUT_PATH = ROOT / "frontend" / "src" / "onboarding" / "airlines.js"

# IATA 코드가 중복될 때 우선 채택할 국가.
PREFERRED_COUNTRY = "대한민국"

# 주요 항공사 영문명. CSV에 영문 컬럼이 없어 여기에서 보완한다.
# 목록에 없는 항공사는 한글명과 IATA 코드로만 검색된다.
ENGLISH_NAMES = {
    # 국내
    "KE": "Korean Air", "OZ": "Asiana Airlines", "7C": "Jeju Air",
    "LJ": "Jin Air", "TW": "T'way Air", "BX": "Air Busan",
    "RS": "Air Seoul", "ZE": "Eastar Jet", "YP": "Air Premia",
    "RF": "Aero K",
    # 일본
    "JL": "Japan Airlines", "NH": "All Nippon Airways", "MM": "Peach Aviation",
    "GK": "Jetstar Japan", "7G": "StarFlyer", "BC": "Skymark Airlines",
    # 중화권
    "CA": "Air China", "MU": "China Eastern Airlines",
    "CZ": "China Southern Airlines", "CX": "Cathay Pacific",
    "HX": "Hong Kong Airlines", "CI": "China Airlines", "BR": "EVA Air",
    "IT": "Tigerair Taiwan",
    # 동남아시아
    "TG": "Thai Airways", "SQ": "Singapore Airlines", "TR": "Scoot",
    "MH": "Malaysia Airlines", "AK": "AirAsia", "D7": "AirAsia X",
    "VN": "Vietnam Airlines", "VJ": "VietJet Air", "PR": "Philippine Airlines",
    "5J": "Cebu Pacific", "GA": "Garuda Indonesia", "SL": "Thai Lion Air",
    "QZ": "Indonesia AirAsia",
    # 중동 · 서남아시아
    "EK": "Emirates", "EY": "Etihad Airways", "QR": "Qatar Airways",
    "TK": "Turkish Airlines", "AI": "Air India", "SV": "Saudia",
    "GF": "Gulf Air",
    # 유럽
    "AF": "Air France", "KL": "KLM", "BA": "British Airways",
    "LH": "Lufthansa", "LX": "Swiss International Air Lines",
    "OS": "Austrian Airlines", "IB": "Iberia", "TP": "TAP Air Portugal",
    "SK": "SAS", "AY": "Finnair", "LO": "LOT Polish Airlines",
    "SU": "Aeroflot", "VS": "Virgin Atlantic", "FR": "Ryanair",
    "U2": "easyJet", "A3": "Aegean Airlines",
    # 북미
    "AA": "American Airlines", "UA": "United Airlines", "DL": "Delta Air Lines",
    "AC": "Air Canada", "AS": "Alaska Airlines", "B6": "JetBlue",
    "WN": "Southwest Airlines", "HA": "Hawaiian Airlines",
    # 오세아니아 · 아프리카
    "QF": "Qantas", "NZ": "Air New Zealand", "JQ": "Jetstar Airways",
    "FJ": "Fiji Airways", "MS": "EgyptAir", "ET": "Ethiopian Airlines",
    "SA": "South African Airways", "KQ": "Kenya Airways",
}

HEADER = """\
/**
 * 항공사 자동완성 목록. `scripts/generate_airlines.py`가 생성하므로 직접 수정하지 않는다.
 * 원본: backend/data/airlines.csv (영문명은 스크립트의 ENGLISH_NAMES에서 보완)
 *
 * code: IATA 항공사 코드 (편명 앞에 붙는 2자리)
 * name: 국문 항공사명
 * name_en: 주요 항공사에만 존재. 없으면 한글명과 코드로만 검색된다.
 */
"""

FOOTER = """
/** CSV 표기는 '에어 서울'처럼 띄어쓰기가 섞여 있어, 비교 시 공백을 무시한다. */
const squash = (value) => value.replace(/\\s+/g, "").toLowerCase();

/** 입력한 이름과 일치하는 항공사(코드 자동 채움용). 띄어쓰기는 무시한다. */
export function findAirlineByName(name) {
  const key = squash(name);
  if (!key) return undefined;
  return AIRLINES.find((airline) => squash(airline.name) === key);
}

/**
 * 입력어로 항공사를 검색한다. 국문명 · 영문명 · IATA 코드로 찾으며,
 * 코드가 정확히 맞거나 앞글자가 일치하는 항목을 먼저 보여준다.
 * ('대한' -> 대한항공 KE / 'KE' -> 대한항공 KE / 'korean' -> 대한항공 KE)
 */
export function searchAirlines(query, limit = 6) {
  const keyword = query.trim();
  if (!keyword) return [];

  const upper = keyword.toUpperCase();
  const key = squash(keyword);
  const exact = [];
  const prefix = [];
  const partial = [];

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
"""


def main() -> None:
    with io.open(CSV_PATH, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    picked: dict[str, dict] = {}
    replaced = 0
    for row in rows:
        code = (row.get("IATA") or "").strip().upper()
        name = (row.get("국문 항공사명") or "").strip()
        country = (row.get("국가") or "").strip()
        if not code or not name:
            continue

        existing = picked.get(code)
        # 중복 코드는 국내 항공사를 우선 채택한다(에어서울 RS, 에어로케이 RF 등).
        if existing is not None:
            if existing["_country"] == PREFERRED_COUNTRY or country != PREFERRED_COUNTRY:
                continue
            replaced += 1

        entry = {"code": code, "name": name, "_country": country}
        name_en = ENGLISH_NAMES.get(code)
        if name_en:
            entry["name_en"] = name_en
        picked[code] = entry

    airlines = sorted(picked.values(), key=lambda item: item["name"])
    for item in airlines:
        item.pop("_country")

    lines = [
        "  " + json.dumps(item, ensure_ascii=False).replace('": ', '": ')
        for item in airlines
    ]
    body = "export const AIRLINES = [\n" + ",\n".join(lines) + ",\n];\n"

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(HEADER + "\n" + body + FOOTER)

    with_en = sum(1 for item in airlines if "name_en" in item)
    print(f"CSV {len(rows)}행 -> 항공사 {len(airlines)}건 생성")
    print(f"  중복 코드 국내 우선 교체: {replaced}건")
    print(f"  영문명 포함: {with_en}건")
    print(f"  출력: {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
