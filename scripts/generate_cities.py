"""backend/data/cities.json -> frontend/src/onboarding/citiesData.ts 생성.

여행지 도시 목록의 원본은 backend/data/cities.json 하나다. 백엔드는 이 파일을 직접 읽고,
프론트는 이 스크립트로 만든 상수 모듈을 쓴다(자동완성 반응 속도). 목록을 고친 뒤 다시 돌리면 된다.

    python scripts/generate_cities.py           # 생성
    python scripts/generate_cities.py --check   # 생성 파일이 원본과 같은지 확인 (다르면 종료 코드 1)

표준 라이브러리만 사용하므로 Django 환경 없이 호스트에서 바로 실행할 수 있다.
"""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "backend" / "data" / "cities.json"
OUT_PATH = ROOT / "frontend" / "src" / "onboarding" / "citiesData.ts"

HEADER = """\
/**
 * 여행지 도시 목록. `scripts/generate_cities.py`가 생성하므로 직접 수정하지 않는다.
 * 원본: backend/data/cities.json (백엔드와 같은 파일)
 *
 * city_code: 서비스 자체 도시 id (예: "tokyo"). IATA 도시 코드가 없는 소도시도 있다.
 * iata: IATA 도시 코드 (없으면 null). 검색과 예전 데이터 호환에만 쓴다.
 * admin1: 소속 도·현 (예: 가나가와현). 자동완성 안내와 검색에 쓴다. 모르면 빈 문자열.
 * aliases: 영문명 등 검색어
 */

import type { CityOption } from "./cities";

export const CITIES: CityOption[] = [
"""


def render() -> str:
    cities = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    lines, region = [HEADER], None
    for city in cities:
        if city["region"] != region:
            region = city["region"]
            lines.append(f"  // {region}\n")
        row = {
            "city": city["name"],
            "city_code": city["id"],
            "iata": city["iata"],
            "admin1": city.get("admin1", ""),
            "aliases": city["aliases"],
            "lat": city["lat"],
            "lng": city["lng"],
        }
        fields = ", ".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in row.items())
        lines.append(f"  {{ {fields} }},\n")
    lines.append("];\n")
    return "".join(lines)


def main() -> None:
    content = render()
    if "--check" in sys.argv:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != content:
            print(f"{OUT_PATH.relative_to(ROOT)} is out of date. Run: python scripts/generate_cities.py")
            sys.exit(1)
        print("cities data is up to date")
        return
    with io.open(OUT_PATH, "w", encoding="utf-8", newline="\n") as file:
        file.write(content)
    count = len(json.loads(JSON_PATH.read_text(encoding="utf-8")))
    print(f"wrote {OUT_PATH.relative_to(ROOT)} ({count} cities)")


if __name__ == "__main__":
    main()
