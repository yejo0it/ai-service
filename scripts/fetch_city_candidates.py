"""Wikidata -> 여행지 도시 후보 CSV (검수용).

backend/data/cities.json에 넣기 전에 사람이 확인할 후보 목록을 만든다.
    python scripts/fetch_city_candidates.py   # -> backend/data/city_candidates.csv

- 출처: Wikidata (CC0). 조회는 이 스크립트를 돌릴 때만 하고, 서비스 실행 중에는 하지 않는다.
- 한국: 특별시·광역시·특별자치시 + 시 + 군 (현재 있는 것만)
- 일본: 47 도도부현의 현청 소재지 + 관광 도시·마을(JP_TOURISM, 일본어 이름으로 찾는다)
- 표시 이름: 한국어 이름에서 행정 접미사(시·군·정·촌 등)를 뗀다. 이름이 같은 곳은 '고성(강원)'처럼 도·현을 붙인다.
- id: 영문 이름으로 만든다. 겹치면 도·현을 붙인다(goseong-gangwon).
- status: new(새로 추가) / merge:<id>(cities.json에 이미 있음) / review(사람 확인 필요, note에 이유)

표준 라이브러리만 사용한다.
"""

import csv
import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CITIES_PATH = ROOT / "backend" / "data" / "cities.json"
OUT_PATH = ROOT / "backend" / "data" / "city_candidates.csv"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "PinRoute-city-data/1.0 (travel planner city list build script)"

# 일본 관광 도시·마을 (현청 소재지가 아닌 곳). 같은 이름의 마을이 많아 (일본어 이름, 도도부현)으로 찾는다.
JP_TOURISM = [
    ("日光市", "栃木県"), ("鎌倉市", "神奈川県"), ("箱根町", "神奈川県"), ("富士河口湖町", "山梨県"), ("富士吉田市", "山梨県"),
    ("軽井沢町", "長野県"), ("松本市", "長野県"), ("白馬村", "長野県"), ("熱海市", "静岡県"), ("伊東市", "静岡県"),
    ("下田市", "静岡県"), ("浜松市", "静岡県"), ("高山市", "岐阜県"), ("白川村", "岐阜県"), ("下呂市", "岐阜県"),
    ("草津町", "群馬県"), ("川越市", "埼玉県"), ("宇治市", "京都府"), ("宮津市", "京都府"), ("姫路市", "兵庫県"),
    ("豊岡市", "兵庫県"), ("伊勢市", "三重県"), ("鳥羽市", "三重県"), ("白浜町", "和歌山県"), ("高野町", "和歌山県"),
    ("倉敷市", "岡山県"), ("尾道市", "広島県"), ("廿日市市", "広島県"), ("出雲市", "島根県"), ("直島町", "香川県"),
    ("琴平町", "香川県"), ("北九州市", "福岡県"), ("太宰府市", "福岡県"), ("別府市", "大分県"), ("阿蘇市", "熊本県"),
    ("佐世保市", "長崎県"), ("指宿市", "鹿児島県"), ("屋久島町", "鹿児島県"), ("石垣市", "沖縄県"), ("宮古島市", "沖縄県"),
    ("名護市", "沖縄県"), ("恩納村", "沖縄県"), ("函館市", "北海道"), ("小樽市", "北海道"), ("富良野市", "北海道"),
    ("美瑛町", "北海道"), ("旭川市", "北海道"), ("倶知安町", "北海道"), ("ニセコ町", "北海道"), ("登別市", "北海道"),
    ("釧路市", "北海道"), ("帯広市", "北海道"), ("弘前市", "青森県"), ("仙北市", "秋田県"), ("尾花沢市", "山形県"),
    ("会津若松市", "福島県"),
]

# 한국 특별시·광역시·특별자치시 (행정 개편으로 Wikidata 분류가 바뀌어도 여행지로 넣는다)
KR_METROS = {
    "Q8684": "특별시", "Q16520": "광역시", "Q20934": "광역시", "Q20927": "광역시", "Q20921": "광역시",
    "Q41283": "광역시", "Q41278": "광역시", "Q20929": "특별자치시",
}
KR_CLASSES = {"Q29045252": "시", "Q17143371": "군"}
# 도 이름 줄임 (같은 이름 구분용)
KR_ADMIN_SHORT = {
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "인천광역시": "인천", "부산광역시": "부산", "대구광역시": "대구", "울산광역시": "울산",
    # Wikidata 기준 2026-07-01 전라남도·광주광역시 통합
    "전남광주통합특별시": "전남",
}
# 같은 이름 구분용 영문 (id 뒤에 붙인다)
KR_ADMIN_EN = {
    "경기": "gyeonggi", "강원": "gangwon", "충북": "chungbuk", "충남": "chungnam", "전북": "jeonbuk", "전남": "jeonnam",
    "경북": "gyeongbuk", "경남": "gyeongnam", "제주": "jeju", "인천": "incheon", "부산": "busan", "대구": "daegu",
    "울산": "ulsan",
}


def query(sparql):
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": sparql, "format": "json"})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["results"]["bindings"]


def value(row, key):
    return row[key]["value"] if key in row else ""


def qid(row, key):
    return value(row, key).rsplit("/", 1)[-1]


def point(row):
    lng, lat = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", value(row, "coord")).groups()
    return round(float(lat), 4), round(float(lng), 4)


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"\b(City|County|Town|Village|Ward|Prefecture|Special City|Metropolitan City|Special Self-Governing City)\b",
                  "", text, flags=re.I)
    text = re.sub(r"[-\s](gun|si|shi|machi|cho|mura|son)$", "", text.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def km(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def korea():
    metros = query("""
    SELECT ?item ?ko ?en ?coord WHERE {
      VALUES ?item { %s }
      ?item wdt:P625 ?coord.
      OPTIONAL { ?item rdfs:label ?ko FILTER(LANG(?ko)="ko") }
      OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en)="en") }
    }""" % " ".join(f"wd:{key}" for key in KR_METROS))
    rows = query("""
    SELECT ?item ?type ?ko ?en ?coord ?adminKo WHERE {
      VALUES ?type { %s }
      ?item wdt:P31 ?type; wdt:P17 wd:Q884; wdt:P625 ?coord.
      FILTER NOT EXISTS { ?item wdt:P576 ?dissolved }
      FILTER NOT EXISTS { ?item p:P31 ?st. ?st ps:P31 ?type; pq:P582 ?ended }
      OPTIONAL { ?item rdfs:label ?ko FILTER(LANG(?ko)="ko") }
      OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en)="en") }
      OPTIONAL { ?item p:P131 ?ps. ?ps ps:P131 ?admin. FILTER NOT EXISTS { ?ps pq:P582 ?e }
                 ?admin rdfs:label ?adminKo FILTER(LANG(?adminKo)="ko") }
    }""" % " ".join(f"wd:{key}" for key in KR_CLASSES))
    items = {}
    for row in metros:
        key = qid(row, "item")
        items.setdefault(key, {
            "country": "KR", "wikidata": key, "raw_ko": value(row, "ko"), "en": value(row, "en"),
            "kind": KR_METROS[key], "admin1": value(row, "ko"), "point": point(row), "notes": [],
        })
        if key == "Q41283":
            items[key]["notes"].append("Wikidata에 2026-07-01 해산(전남광주통합특별시)으로 기록 - 광주광역시로 유지")
    for row in rows:
        if qid(row, "item") in items:
            continue
        item = items.setdefault(qid(row, "item"), {
            "country": "KR", "wikidata": qid(row, "item"), "raw_ko": value(row, "ko"), "en": value(row, "en"),
            "kind": KR_CLASSES[qid(row, "type")], "admin1": "", "point": point(row), "notes": [],
        })
        admin = value(row, "adminKo")
        # 소속 도: 대한민국(국가) 같은 상위 값보다 도·광역시를 고른다.
        if admin in KR_ADMIN_SHORT and not item["admin1"]:
            # Wikidata의 전남광주통합특별시(2026-07-01~) 소속은 확인 전까지 전라남도로 표기한다.
            item["admin1"] = "전라남도" if admin == "전남광주통합특별시" else admin
    for item in items.values():
        name = re.sub(r"(특별자치시|특별시|광역시)$", "", item["raw_ko"])
        if item["kind"] in ("시", "군"):
            name = re.sub(r"(시|군)$", "", name)
        item["name"] = name
        item["short_admin"] = KR_ADMIN_SHORT.get(item["admin1"], "")
        item["admin_en"] = KR_ADMIN_EN.get(item["short_admin"], "")
    return list(items.values())


def japan():
    prefectures = query("""
    SELECT ?pref ?prefKo ?prefEn ?cap ?ko ?en ?coord WHERE {
      ?pref wdt:P31 wd:Q50337.
      FILTER NOT EXISTS { ?pref wdt:P576 ?d }
      FILTER NOT EXISTS { ?pref p:P31 ?st. ?st ps:P31 wd:Q50337; pq:P582 ?e }
      ?pref p:P36 ?cs. ?cs ps:P36 ?cap. FILTER NOT EXISTS { ?cs pq:P582 ?e2 }
      ?cap wdt:P625 ?coord.
      OPTIONAL { ?pref rdfs:label ?prefKo FILTER(LANG(?prefKo)="ko") }
      OPTIONAL { ?pref rdfs:label ?prefEn FILTER(LANG(?prefEn)="en") }
      OPTIONAL { ?cap rdfs:label ?ko FILTER(LANG(?ko)="ko") }
      OPTIONAL { ?cap rdfs:label ?en FILTER(LANG(?en)="en") }
    }""")
    tourism = query("""
    SELECT ?item ?ja ?prefJa ?ko ?en ?coord ?prefKo ?prefEn WHERE {
      VALUES (?ja ?prefJa) { %s }
      ?item rdfs:label ?ja; wdt:P17 wd:Q17; wdt:P625 ?coord.
      ?item wdt:P131+ ?pref. ?pref wdt:P31 wd:Q50337; rdfs:label ?prefJa. FILTER NOT EXISTS { ?pref wdt:P576 ?d }
      FILTER NOT EXISTS { ?item wdt:P576 ?gone }
      OPTIONAL { ?item rdfs:label ?ko FILTER(LANG(?ko)="ko") }
      OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en)="en") }
      OPTIONAL { ?pref rdfs:label ?prefKo FILTER(LANG(?prefKo)="ko") }
      OPTIONAL { ?pref rdfs:label ?prefEn FILTER(LANG(?prefEn)="en") }
    }""" % " ".join(f'("{name}"@ja "{pref}"@ja)' for name, pref in JP_TOURISM))

    items = {}
    for row in prefectures:
        if value(row, "ko").endswith("구"):
            continue  # 도쿄도: 현청 소재지가 신주쿠구로 되어 있다. 여행지는 기존 '도쿄'를 쓴다.
        key = qid(row, "cap")
        items.setdefault(key, {
            "country": "JP", "wikidata": key, "raw_ko": value(row, "ko"), "en": value(row, "en"),
            "kind": "현청 소재지", "admin1": value(row, "prefKo"), "admin_en": slug(value(row, "prefEn")),
            "point": point(row), "notes": [],
        })
    found = set()
    for row in tourism:
        key = qid(row, "item")
        found.add((value(row, "ja"), value(row, "prefJa")))
        if key in items:
            continue
        items[key] = {
            "country": "JP", "wikidata": key, "raw_ko": value(row, "ko"), "en": value(row, "en"),
            "kind": "관광", "admin1": value(row, "prefKo"), "admin_en": slug(value(row, "prefEn")),
            "point": point(row), "notes": [],
        }
    for item in items.values():
        item["name"] = re.sub(r"(시|정|촌|구|마치|무라)$", "", item["raw_ko"]) if item["raw_ko"] else ""
        item["short_admin"] = re.sub(r"(현|부|도)$", "", item["admin1"]) if item["admin1"] != "홋카이도" else "홋카이도"
    missing = sorted(f"{name}({pref})" for name, pref in set(JP_TOURISM) - found)
    return list(items.values()), missing


def main():
    existing = json.loads(CITIES_PATH.read_text(encoding="utf-8"))
    kr = korea()
    jp, jp_missing = japan()
    rows = kr + jp

    # 같은 나라에서 표시 이름이 겹치면 도·현을 붙인다.
    for country in ("KR", "JP"):
        names = {}
        for item in rows:
            if item["country"] == country:
                names.setdefault(item["name"], []).append(item)
        for name, same in names.items():
            if len(same) > 1 and name:
                # 특별·광역시가 끼어 있으면 그 도시는 이름 그대로 두고, 나머지에만 도·현을 붙인다.
                metro = next((item for item in same if item["kind"] in KR_METROS.values()), None)
                for item in same:
                    if item is metro:
                        continue
                    item["name"] = f"{name}({item['short_admin']})"
                    item["dup"] = True
                    item["notes"].append("이름이 같은 곳이 있어 도·현을 붙임")

    used_ids = {city["id"] for city in existing}
    for item in rows:
        if not item["raw_ko"]:
            item["notes"].append("한국어 이름 없음 - 직접 입력 필요")
        if not item["admin1"]:
            item["notes"].append("소속 도·현을 찾지 못함")
        # 기존 도시와 같은 곳(15km 이내 + 이름 일치, 또는 3km 이내)이면 합친다.
        match = next((city for city in existing if city["country"] == item["country"] and (
            km(item["point"], (city["lat"], city["lng"])) < 3
            or (km(item["point"], (city["lat"], city["lng"])) < 15 and city["name"] in item["name"])
        )), None)
        if match:
            item["status"], item["id"] = f"merge:{match['id']}", match["id"]
            continue
        base = slug(item["en"]) or item["wikidata"].lower()
        if item.get("dup") and item.get("admin_en"):
            base = f"{base}-{item['admin_en']}"
        candidate = base if base not in used_ids else f"{base}-{item.get('admin_en') or item['country'].lower()}"
        if candidate in used_ids:
            candidate = f"{base}-{item['wikidata'].lower()}"
            item["notes"].append("id가 겹쳐 Wikidata 번호를 붙임")
        item["id"] = candidate
        used_ids.add(candidate)
        item["status"] = "review" if item["notes"] and any("없음" in n or "찾지" in n or "검토" in n for n in item["notes"]) else "new"

    rows.sort(key=lambda item: (item["country"], item["admin1"], item["name"]))
    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["status", "country", "id", "name", "admin1", "kind", "raw_ko", "en", "lat", "lng",
                         "wikidata", "note"])
        for item in rows:
            writer.writerow([item["status"], item["country"], item["id"], item["name"], item["admin1"], item["kind"],
                             item["raw_ko"], item["en"], *item["point"], item["wikidata"], " / ".join(item["notes"])])

    counts = {}
    for item in rows:
        key = (item["country"], item["status"].split(":")[0])
        counts[key] = counts.get(key, 0) + 1
    print(f"wrote {OUT_PATH.relative_to(ROOT)}: {len(rows)} rows", counts)
    if jp_missing:
        print("Wikidata에서 찾지 못한 일본 관광지:", ", ".join(jp_missing))


if __name__ == "__main__":
    main()
