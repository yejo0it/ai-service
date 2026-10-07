# frontend/src/data — 프론트 참조 데이터

검색 함수와 타입은 `src/onboarding/*.ts`에 있고, 데이터는 이 폴더의 JSON에 있습니다.

| 파일 | 원본 | 수정 방법 | 쓰는 곳 |
|---|---|---|---|
| `cities.json` | `backend/data/cities.json` | 원본을 고친 뒤 `python scripts/generate_cities.py` (직접 수정 금지) | `onboarding/cities.ts` |
| `airlines.json` | `backend/data/airlines.csv`, `backend/data/airline_names_en.json` | 원본을 고친 뒤 `python scripts/generate_airlines.py` (직접 수정 금지) | `onboarding/airlines.ts` |
| `airports.json` | 이 파일이 원본 (백엔드는 쓰지 않음) | 이 파일을 직접 고친다 | `onboarding/airports.ts` |

한 줄에 한 항목으로 두어 데이터 변경 diff를 읽기 쉽게 합니다.
