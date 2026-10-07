"""backend/data/cities.json -> frontend/src/data/cities.json 생성.

여행지 도시 목록의 원본은 backend/data/cities.json 하나다. 백엔드는 이 파일을 직접 읽고,
프론트는 이 스크립트로 만든 데이터 파일을 쓴다(자동완성 반응 속도). 목록을 고친 뒤 다시 돌리면 된다.
프론트용 필드 이름(city, city_code ...)으로 바꿔 담는다. 검색 함수는 frontend/src/onboarding/cities.ts에 있다.

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
OUT_PATH = ROOT / "frontend" / "src" / "data" / "cities.json"


def render() -> str:
    cities = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    rows = [
        {
            "city": city["name"],
            "city_code": city["id"],
            "iata": city["iata"],
            "admin1": city.get("admin1", ""),
            "region": city["region"],
            "aliases": city["aliases"],
            "lat": city["lat"],
            "lng": city["lng"],
        }
        for city in cities
    ]
    # 한 줄에 한 도시 (diff를 읽기 쉽게)
    lines = ",\n".join("  " + json.dumps(row, ensure_ascii=False) for row in rows)
    return "[\n" + lines + "\n]\n"


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
