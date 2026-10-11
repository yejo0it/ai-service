"""검수한 후보 CSV -> backend/data/cities.json 반영.

    python scripts/fetch_city_candidates.py   # Wikidata -> backend/data/city_candidates.csv (검수)
    python scripts/apply_city_candidates.py   # 검수한 CSV -> backend/data/cities.json
    python scripts/generate_cities.py         # cities.json -> 프론트 도시 데이터
    (백엔드는 cities.json을 처음 한 번만 읽으므로, 반영하려면 백엔드를 다시 시작한다)

- status new: 새 도시로 추가한다(나라 묶음 안에서 도·현, 이름 순).
- status merge:<id>: 이미 있는 도시다. 이름·좌표는 그대로 두고 소속 도·현(admin1)만 채운다.
- 다른 status(review 등)는 넣지 않는다.
- 검색어(aliases): 영문 이름(행정 단위 단어를 뺀 것)과, 표시 이름과 다른 한국어 행정 이름(예: 가평군).
- 여러 번 돌려도 결과가 같다(이미 있는 id는 다시 추가하지 않고, 소속 도·현만 CSV에 맞춘다).

표준 라이브러리만 사용한다.
"""

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CITIES_PATH = ROOT / "backend" / "data" / "cities.json"
CANDIDATES_PATH = ROOT / "backend" / "data" / "city_candidates.csv"
REGION = {"KR": "한국", "JP": "일본"}
# 후보 목록에 없는 기존 도시의 소속 도·현
EXTRA_ADMIN1 = {"yufuin": "오이타현"}


def english(name):
    """'Gapyeong County' -> 'Gapyeong', 'Hakone' -> 'Hakone'"""
    name = re.sub(r"\b(City|County|Town|Village|Ward|Prefecture|Special City|Metropolitan City|"
                  r"Special Self-Governing City)\b", "", name)
    name = re.sub(r"[-\s](gun|si|shi|machi|cho|mura|son)$", "", name.strip(), flags=re.I)
    return re.sub(r"\s+", " ", name).strip(" ,-")


def main():
    cities = json.loads(CITIES_PATH.read_text(encoding="utf-8"))
    by_id = {city["id"]: city for city in cities}
    with CANDIDATES_PATH.open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    added = {}
    merged = 0
    for row in rows:
        status = row["status"]
        if status.startswith("merge:"):
            city = by_id.get(status.split(":", 1)[1])
            if city and row["admin1"]:
                city["admin1"] = row["admin1"]
                merged += 1
            continue
        if status != "new":
            continue
        if row["id"] in by_id:
            # 이미 넣은 도시: 검수 후 바뀐 소속 도·현만 맞춘다.
            if row["admin1"]:
                by_id[row["id"]]["admin1"] = row["admin1"]
            continue
        aliases = [alias for alias in (english(row["en"]), row["raw_ko"]) if alias and alias != row["name"]]
        city = {
            "id": row["id"], "name": row["name"], "region": REGION[row["country"]], "country": row["country"],
            "iata": None, "admin1": row["admin1"], "aliases": aliases,
            "lat": float(row["lat"]), "lng": float(row["lng"]),
        }
        added.setdefault(city["region"], []).append(city)
        by_id[city["id"]] = city
    for city_id, admin1 in EXTRA_ADMIN1.items():
        if city_id in by_id:
            by_id[city_id]["admin1"] = admin1

    # 나라 묶음(region) 순서는 그대로, 각 묶음 끝에 새 도시를 도·현·이름 순으로 붙인다.
    result, seen_regions = [], []
    for city in cities:
        if city["region"] not in seen_regions:
            seen_regions.append(city["region"])
    for region in seen_regions:
        result += [city for city in cities if city["region"] == region]
        result += sorted(added.get(region, []), key=lambda city: (city["admin1"], city["name"]))
    # 필드 순서 맞추기 (admin1은 소속을 아는 도시만)
    order = ["id", "name", "region", "country", "iata", "admin1", "aliases", "lat", "lng"]
    result = [{key: city[key] for key in order if key in city and (key != "admin1" or city[key])} for city in result]

    body = ",\n".join("  " + json.dumps(city, ensure_ascii=False) for city in result)
    CITIES_PATH.write_text("[\n" + body + "\n]\n", encoding="utf-8", newline="\n")
    print(f"cities.json: {len(cities)} -> {len(result)} cities "
          f"(+{sum(len(v) for v in added.values())} new, {merged} existing got admin1)")


if __name__ == "__main__":
    main()
