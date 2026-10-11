"""backend/data/airlines.csv (+ airline_names_en.json) -> frontend/src/data/airlines.json 생성.

항공사 목록은 자주 바뀌지 않으므로 프론트 데이터 파일로 내려 자동완성 반응 속도를 확보한다.
CSV가 원본이며, 목록을 고친 뒤 이 스크립트를 다시 돌리면 된다. 검색 함수는 frontend/src/onboarding/airlines.ts에 있다.

    python scripts/generate_airlines.py           # 생성
    python scripts/generate_airlines.py --check   # 생성 파일이 원본과 같은지 확인 (다르면 종료 코드 1)

- 영문명: backend/data/airline_names_en.json (IATA 코드 -> 영문명). 목록에 없는 항공사는 한글명과 코드로만 검색된다.
- IATA 코드가 겹치면 국내 항공사를 우선 채택한다(에어서울 RS, 에어로케이 RF 등).

표준 라이브러리만 사용하므로 Django 환경 없이 호스트에서 바로 실행할 수 있다.
"""

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "backend" / "data" / "airlines.csv"
NAMES_EN_PATH = ROOT / "backend" / "data" / "airline_names_en.json"
OUT_PATH = ROOT / "frontend" / "src" / "data" / "airlines.json"

# IATA 코드가 중복될 때 우선 채택할 국가.
PREFERRED_COUNTRY = "대한민국"


def build() -> tuple[str, dict]:
    """CSV -> (airlines.json 내용, 통계)"""
    with io.open(CSV_PATH, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    english_names = json.loads(NAMES_EN_PATH.read_text(encoding="utf-8"))

    picked: dict[str, dict] = {}
    replaced = 0
    for row in rows:
        code = (row.get("IATA") or "").strip().upper()
        name = (row.get("국문 항공사명") or "").strip()
        country = (row.get("국가") or "").strip()
        if not code or not name:
            continue

        existing = picked.get(code)
        if existing is not None:
            if existing["_country"] == PREFERRED_COUNTRY or country != PREFERRED_COUNTRY:
                continue
            replaced += 1

        entry = {"code": code, "name": name, "_country": country}
        name_en = english_names.get(code)
        if name_en:
            entry["name_en"] = name_en
        picked[code] = entry

    airlines = sorted(picked.values(), key=lambda item: item["name"])
    for item in airlines:
        item.pop("_country")

    # 한 줄에 한 항공사 (diff를 읽기 쉽게)
    content = "[\n" + ",\n".join("  " + json.dumps(item, ensure_ascii=False) for item in airlines) + "\n]\n"
    stats = {
        "rows": len(rows),
        "airlines": len(airlines),
        "replaced": replaced,
        "with_en": sum(1 for item in airlines if "name_en" in item),
    }
    return content, stats


def main() -> None:
    content, stats = build()
    if "--check" in sys.argv:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != content:
            print(f"{OUT_PATH.relative_to(ROOT)} is out of date. Run: python scripts/generate_airlines.py")
            sys.exit(1)
        print("airlines data is up to date")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    print(f"CSV {stats['rows']} rows -> {stats['airlines']} airlines "
          f"(duplicates replaced: {stats['replaced']}, with English name: {stats['with_en']})")
    print(f"  wrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
