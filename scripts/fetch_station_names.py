"""Wikidata -> 일본 역 이름(일본어·한국어) 데이터.

NAVITIME 이동 안내의 역 이름을 한국어로 보여주기 위한 참조 데이터를 만든다.
    python scripts/fetch_station_names.py            # -> backend/data/station_names_ja_ko.json
    python scripts/fetch_station_names.py --check    # 파일을 쓰지 않고 내려받은 결과의 요약만 본다

- 출처: Wikidata (https://www.wikidata.org, CC0 1.0 퍼블릭 도메인). 조회는 이 스크립트를 돌릴 때만 하고,
  서비스 실행 중에는 외부 서비스를 부르지 않는다. 다시 내려받으면 같은 형식의 파일이 새로 만들어진다.
- 대상: 일본(P17=Q17)의 좌표(P625)가 있는 항목 중 일본어 이름이 '駅'으로, 한국어 이름이 '역'으로 끝나는 것.
  (Wikidata에는 역 분류(instance of)가 항목마다 달라 분류로 거르면 신주쿠·시부야 같은 큰 역이 빠진다.)
- 한국어 이름이 없는 역은 들어가지 않는다. 사용하는 쪽(trips/station_names.py)은 없으면 원어를 그대로 보여준다.
- 이름은 사용자들이 쓴 값이라 표기가 거칠 수 있다. 읽기가 의심스러운 항목은 flag를 달아 둔다(아래 SUSPECT 규칙).
  사용하는 쪽은 flag가 있는 항목을 쓰지 않고 원어를 보여준다. 품질 점검 결과는 backend/data/README.md를 참고한다.

표준 라이브러리만 사용한다.
"""

import json
import math
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "backend" / "data" / "station_names_ja_ko.json"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "PinRoute-station-data/1.0 (travel planner station name build script)"

QUERY = """SELECT DISTINCT ?s ?ja ?ko ?c WHERE {
  ?s wdt:P17 wd:Q17 .
  ?s wdt:P625 ?c .
  ?s rdfs:label ?ko FILTER(LANG(?ko) = "ko" && STRENDS(?ko, "역"))
  ?s rdfs:label ?ja FILTER(LANG(?ja) = "ja" && STRENDS(?ja, "駅"))
}"""


def fetch_rows():
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": QUERY, "format": "json"})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=170) as response:
        return json.loads(response.read().decode())["results"]["bindings"]


KANJI = re.compile(r"[一-鿿]")
HANGUL_ONLY = re.compile(r"[^가-힣]")


def suspect(ja, ko):
    """
    한자 수보다 한국어 음절이 적으면 일본어 읽기가 아니라 한국 한자음으로 옮겼거나 다른 역 이름이 붙은 것일 수 있다
    (예: 国府 -> 고, 京阪大津京 -> 오지야마). 倶知安(굿찬)·国府津(고즈)처럼 정말 짧은 읽기도 걸리지만, 틀린 이름을 보여주는
    것보다 원어를 보여주는 쪽이 안전하다.
    """
    kanji = len(KANJI.findall(ja[:-1]))
    syllables = len(HANGUL_ONLY.sub("", ko[:-1]))
    return kanji > 0 and syllables < kanji


def parse_point(value):
    """'Point(139.70133 35.65851)' -> (lat, lng)"""
    lng, lat = value[value.index("(") + 1 : value.index(")")].split()
    return round(float(lat), 5), round(float(lng), 5)


def build(rows):
    stations = {}
    for row in rows:
        lat, lng = parse_point(row["c"]["value"])
        if not (math.isfinite(lat) and math.isfinite(lng)):
            continue
        entry = {"ja": row["ja"]["value"].strip(), "ko": row["ko"]["value"].strip(), "lat": lat, "lng": lng}
        item = {**entry, "qid": row["s"]["value"].rsplit("/", 1)[-1]}
        if suspect(entry["ja"], entry["ko"]):
            item["flag"] = "suspect_reading"
        stations[(entry["ja"], entry["ko"], lat, lng)] = item
    return sorted(stations.values(), key=lambda e: (e["ja"], e["lat"], e["lng"]))


def main():
    check_only = "--check" in sys.argv
    stations = build(fetch_rows())
    flagged = sum(1 for s in stations if s.get("flag"))
    print(f"역 {len(stations)}건 (고유 일본어 이름 {len({s['ja'] for s in stations})}개, 읽기 의심 flag {flagged}건)")
    if check_only:
        return
    payload = {
        "_meta": {
            "source": "Wikidata (https://www.wikidata.org/)",
            "license": "CC0 1.0",
            "downloaded": date.today().isoformat(),
            "refresh": "python scripts/fetch_station_names.py",
            "query": QUERY,
            "count": len(stations),
            "flagged": flagged,
            "note": "ko는 Wikidata의 한국어 이름 그대로다(띄어쓰기 정리 등은 사용하는 쪽에서 한다). qid는 Wikidata 항목 번호. flag가 있는 항목은 쓰지 않는다.",
        },
        "stations": stations,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"저장: {OUT_PATH.relative_to(ROOT)} ({OUT_PATH.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
