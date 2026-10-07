# backend/data — 정적 참조 데이터 원본

코드에 하드코딩하지 않는 참조 데이터의 **원본**입니다. 프론트용 데이터는 이 파일들에서 스크립트로 생성합니다.

| 파일 | 내용 | 쓰는 곳 | 프론트 생성 |
|---|---|---|---|
| `cities.json` | 여행지 도시 (자체 도시 id, 이름, 도·현, 좌표, 검색어) | `trips/cities.py` | `python scripts/generate_cities.py` → `frontend/src/data/cities.json` |
| `city_candidates.csv` | 도시 추가 검수 기록 (Wikidata 후보) | `scripts/apply_city_candidates.py` | — |
| `currencies.json` | 통화 표시 정보, 나라별 현지 통화 (환율 위젯) | `trips/travel_info.py`, `trips/cities.py` | — |
| `airlines.csv` | 항공사 목록 | `python manage.py import_airlines` (DB) | `python scripts/generate_airlines.py` → `frontend/src/data/airlines.json` |
| `airline_names_en.json` | 주요 항공사 영문명 (IATA 코드 → 영문명) | — | `generate_airlines.py`가 함께 읽음 |

- 백엔드는 데이터 파일을 처음 한 번만 읽어 메모리에 둡니다(`trips/reference_data.py`). 파일을 고치면 **백엔드를 다시 시작**해야 반영됩니다.
- 프론트 생성 파일이 원본과 같은지는 `--check`로 확인합니다 (`python scripts/generate_cities.py --check`, `python scripts/generate_airlines.py --check`).
- 도시 데이터 출처: Wikidata (CC0). 갱신 순서는 `scripts/fetch_city_candidates.py` → 검수 → `scripts/apply_city_candidates.py` → `scripts/generate_cities.py`.
