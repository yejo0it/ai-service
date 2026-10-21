# backend/data — 정적 참조 데이터 원본

코드에 하드코딩하지 않는 참조 데이터의 **원본**입니다. 프론트용 데이터는 이 파일들에서 스크립트로 생성합니다.

| 파일 | 내용 | 쓰는 곳 | 프론트 생성 |
|---|---|---|---|
| `cities.json` | 여행지 도시 (자체 도시 id, 이름, 도·현, 좌표, 검색어) | `trips/cities.py` | `python scripts/generate_cities.py` → `frontend/src/data/cities.json` |
| `city_candidates.csv` | 도시 추가 검수 기록 (Wikidata 후보) | `scripts/apply_city_candidates.py` | — |
| `currencies.json` | 통화 표시 정보, 나라별 현지 통화 (환율 위젯) | `trips/travel_info.py`, `trips/cities.py` | — |
| `airlines.csv` | 항공사 목록 | `python manage.py import_airlines` (DB) | `python scripts/generate_airlines.py` → `frontend/src/data/airlines.json` |
| `airline_names_en.json` | 주요 항공사 영문명 (IATA 코드 → 영문명) | — | `generate_airlines.py`가 함께 읽음 |
| `station_names_ja_ko.json` | 일본 역 이름 일본어·한국어 + 좌표 (Wikidata, 8,035건) | `trips/station_names.py` (이동 구간 안내) | — |
| `station_name_overrides.json` | 직접 확인한 한국어 역 이름 (NAVITIME node_id 기준, Wikidata보다 우선) | `trips/station_names.py` | — |

- 백엔드는 데이터 파일을 처음 한 번만 읽어 메모리에 둡니다(`trips/reference_data.py`). 파일을 고치면 **백엔드를 다시 시작**해야 반영됩니다.
- 프론트 생성 파일이 원본과 같은지는 `--check`로 확인합니다 (`python scripts/generate_cities.py --check`, `python scripts/generate_airlines.py --check`).
- 도시 데이터 출처: Wikidata (CC0). 갱신 순서는 `scripts/fetch_city_candidates.py` → 검수 → `scripts/apply_city_candidates.py` → `scripts/generate_cities.py`.

## station_names_ja_ko.json (일본 역 이름 일본어·한국어)

NAVITIME 이동 안내의 역 이름을 한국어로 보여주기 위한 참조 데이터입니다.

- **출처:** Wikidata (https://www.wikidata.org/), CC0 1.0. 파일 안 `_meta`에 출처·라이선스·내려받은 날짜·조회 쿼리·건수가 들어 있습니다.
- **갱신 방법:** `python scripts/fetch_station_names.py` (표준 라이브러리만 사용, 표준 출력에 건수 요약). 갱신하면 같은 형식으로 파일이 새로 만들어지고, 백엔드를 다시 시작해야 반영됩니다. 파일을 쓰지 않고 요약만 보려면 `--check`.
- **대상:** 일본(P17=Q17)의 좌표(P625)가 있는 항목 중 일본어 이름이 `駅`으로, 한국어 이름이 `역`으로 끝나는 것. 한국어 이름이 없는 역은 들어가지 않습니다(없으면 원어를 그대로 보여줌).
- **형식:** `{"_meta": {...}, "stations": [{"ja", "ko", "lat", "lng", "qid", "flag"?}]}`. `qid`는 Wikidata 항목 번호이고, `flag`는 아래의 읽기 의심 항목 표시입니다. `ko`는 Wikidata 이름 그대로이며 띄어쓰기 정리(` 역` → `역`)는 사용하는 쪽에서 합니다.
- **읽기 의심 flag:** 한자 수보다 한국어 음절이 적은 이름(한국 한자음으로 옮겼거나 다른 역 이름이 붙은 경우, 예: 京阪大津京駅 → "오지야마 역")에는 `"flag": "suspect_reading"`을 달았고 사용하는 쪽은 이 항목을 쓰지 않습니다(원어 유지). 倶知安(굿찬)처럼 실제로 짧은 읽기도 걸리지만, 틀린 이름을 보여주는 것보다 안전하다고 보았습니다.
- **매칭:** 이름(끝의 `駅`·괄호 설명 제거)으로 찾고, 좌표를 알면 가장 가까운 항목(800m 이내)만 씁니다. 같은 이름의 서로 다른 역이 있어(예: 三田駅 미타/산다) 좌표 없이 찾을 때는 한국어가 하나로 정해지는 경우에만 씁니다. 불확실하면 원어를 유지합니다.
- **사람이 확인한 예외:** `station_name_overrides.json`(NAVITIME `node_id` → 한국어 이름)을 두면 이 데이터보다 먼저 씁니다(파일이 없으면 무시).
- **사용 여부:** 기본은 켜져 있습니다(`STATION_NAMES_ENABLED=1`). `STATION_NAMES_ENABLED=0`으로 끄면 파일을 읽지 않고 역 이름은 원어로 보입니다.
- **예외 목록 (`station_name_overrides.json`):** NAVITIME `node_id` → 직접 확인한 한국어 이름(`{"ko", "ja", "source", "verified"}`). 항상 Wikidata 데이터보다 먼저 쓰고, 출처를 `source`에 적습니다. 확인하지 못한 이름은 넣지 않습니다.
- **알려진 한계:** Wikidata의 한국어 이름이 옛 이름인 경우가 있습니다(예: 도쿄 모노레일 羽田空港第2ターミナル는 '하네다 공항 제2빌딩역'). 확인한 이름을 예외 목록에 추가해 바로잡습니다.

## 미변환 이름 수집 (사전 보완용)

NAVITIME 이동 안내에서 한국어로 바꾸지 못한 **역·노선 이름**을 로그로 모읍니다(`trips/untranslated.py`).

- **기록 위치:** `backend/logs/untranslated_names.jsonl` (`UNTRANSLATED_LOG_PATH`로 변경, git에는 올라가지 않음). 1MB씩 3개까지 돌려 씁니다.
- **기록 내용:** 변환하지 못한 이름과 식별 정보뿐입니다. 역은 이름 + NAVITIME `node_id` + 좌표(행선지는 이름만), 노선은 이름 + 운영사 이름입니다. 경로·시각·요금·사용자·여행 정보는 기록하지 않습니다. 같은 이름은 프로세스당 한 번만 남깁니다.
- **확인:** `python manage.py untranslated_names` (많이 나온 순, `--kind station|line`, `--limit N`, `--json`).
- **보완:**
  - 역 → `station_name_overrides.json`에 `node_id`로 **직접 확인한 한국어 이름**을 넣습니다. (히라가나·가타카나 표기는 한자 이름 데이터와 맞지 않아 여기에 넣어야 합니다.)
  - 노선·운영사 → `trips/line_names.py`의 `LINES`·`OPERATORS`, `trips/station_names.py`의 `COMPANIES`에 추가합니다.
  - 확인하지 못한 이름은 넣지 않고 원어로 둡니다.
- **끄기:** `UNTRANSLATED_LOG_ENABLED=0`. 로그를 쓸 수 없는 환경(읽기 전용 등)에서는 조용히 건너뛰며 이동 안내에는 영향이 없습니다. 테스트 실행 중에는 쓰지 않습니다.
