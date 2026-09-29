# AI SERVICE

## 과정 / 학습 목표

오픈소스 기반 AI 기술을 활용하여 **실제 배포 가능한 AI 데모 서비스를 1개 이상 완성**하는 것을 목표로 합니다.

이 저장소에는 과정을 진행하며 실습 코드, 프로젝트 진행 과정을 기록합니다.

### 현재 위치

* Claude Code, Codex 등 AI Coding Agent의 개념과 활용 사례를 알고 있는 단계
* Python/Django 기반 백엔드 개발 경험은 있지만, LLM 및 AI Agent 개발 경험은 부족한 상태

### 개인 목표

* Agent, Model, AI Platform 등을 활용한 **AI Agent의 전체 동작 흐름** 이해
* MCP, Prompt Engineering, RAG, Tool Calling 등 핵심 기술 학습
* 목적에 맞는 AI 스택과 오픈소스 도구를 선택하고 활용할 수 있는 역량 확보
* 실제 서비스 형태로 배포 가능한 AI 데모 프로젝트 1개 이상 완성
* 학습 과정과 시행착오를 GitHub에 꾸준히 기록하여 기술 포트폴리오 구축

## 관심 트랙

* 🥇 추천 / 분류-1순위

사용자 데이터를 기반으로 개인화 추천 및 매칭 서비스를 구현하는 프로젝트에 가장 관심이 있습니다.
백엔드 개발 경험을 살려 추천 로직과 AI 모델을 실제 서비스 형태로 연결하는 과정을 경험해 보고 싶습니다.

* 🥈 문서 기반 RAG-2순위

RAG(Retrieval-Augmented Generation)를 활용한 문서 검색 및 질의응답 서비스에 관심이 있습니다.
기업 문서, 사내 지식베이스, FAQ 등 실무에서 활용 가능한 서비스를 직접 구현하며 AI 서비스 아키텍처를 경험해 보고 싶습니다.

---

# PinRoute — 온보딩 MVP

여행 동선 최적화 서비스 PinRoute의 온보딩(Step 1~3) 백엔드 API와 프론트엔드 위저드.

```
backend/    Django 5 + DRF (PostgreSQL)
frontend/   React 18 + Tailwind CSS 4 + Vite
(docker compose로 db · backend · frontend 3개 컨테이너를 함께 띄운다)
```

## 온보딩 흐름

| Step | 입력 | 저장 위치 |
| --- | --- | --- |
| 1 | 여행지 | `Trip.destinations` |
| 2 | 항공권 정보 **또는** 날짜만 등록 | `Trip.flight_info` / `Trip.start_date`, `end_date`, `date_source` |
| 3 | 호텔 (Skip 가능) | `Hotel` (Trip 당 0개 이상) |


## API

| Method | URL | 설명 |
| --- | --- | --- |
| GET/POST | `/api/v1/trips/` | 여행 목록 / 생성 (`hotels: [...]` 중첩 생성 지원, `?destination=` 로 도시명·도시코드 부분 검색) |
| GET/PATCH/DELETE | `/api/v1/trips/{id}/` | 여행 상세 / 부분 수정 / 삭제 |
| GET/POST | `/api/v1/trips/{id}/hotels/` | 해당 여행의 숙소 목록 / 추가 (배열도 허용) |
| GET/POST | `/api/v1/hotels/` | 숙소 전체 / 생성 (`?trip={id}` 필터) |
| GET/PATCH/DELETE | `/api/v1/hotels/{id}/` | 숙소 상세 / 수정 / 삭제 |

`flight_info`를 보내면 `start_date`/`end_date`가 비어 있어도 `departure_at`, `return_arrival_at`에서 자동으로 채워지고
`date_source`가 `flight`로 설정된다. 숙소 일정이 여행 기간을 벗어나면 400을 반환한다.

### 요청 예시

```jsonc
POST /api/v1/trips/
{
  // 여행지는 1개 이상. 배열 순서가 곧 도시 이동 순서다.
  "destinations": [
    {"city": "도쿄", "city_code": "TYO"},
    {"city": "나고야", "city_code": "NGO"},
    {"city": "오사카", "city_code": "OSA"}
  ],
  "date_source": "flight",
  "flight_info": {
    "airline": "대한항공",
    "flight_number": "KE001",
    "departure_at": "2026-09-01T10:30",
    "return_arrival_at": "2026-09-05T18:00"
  },
  "hotels": [
    { "name": "신주쿠 호텔", "address": "도쿄도 신주쿠구", "check_in": "2026-09-01", "check_out": "2026-09-04" }
  ]
}
```

호텔을 Skip하면 `"hotels": []`, 날짜만 등록하면 `"flight_info": null` + `start_date`/`end_date`를 보낸다.

## 실행 (Docker — 권장)

```bash
cp .env.example .env          # 비밀번호/시크릿만 필요에 맞게 수정
docker compose up -d --build
docker compose logs -f backend
```

| 서비스 | 호스트 주소 | 컨테이너 내부 | 비고 |
| --- | --- | --- | --- |
| frontend | http://localhost:8002 | `frontend:8002` | Vite dev server (`--host 0.0.0.0`) |
| backend | http://localhost:8003/api/v1/ | `backend:8000` | Django runserver, `/admin/`도 동일 호스트 |
| db | `localhost:5433` | `db:5432` | PostgreSQL 16, DBeaver/psql 등에서 직접 접속 |

```bash
# DB 직접 접속 예시
psql -h localhost -p 5433 -U pinroute -d pinroute

docker compose down       # 컨테이너만 정리(데이터 유지)
docker compose down -v    # pgdata 볼륨까지 삭제(초기화)
```

**포트 선택 이유**: 이 머신에서 5432는 다른 프로젝트의 Postgres, 8001은 다른 nginx가 이미 점유 중이라
DB는 5433, 백엔드는 8003으로 바인딩했다. 바꾸려면 `docker-compose.yml`의 `ports`와 `.env`의 `VITE_API_URL`을 함께 수정한다.

### 컨테이너 구성에서 주의할 점

- **API 주소는 컨테이너명이 아니라 호스트 주소**를 쓴다. `frontend` 컨테이너의 React 코드는 브라우저에서 실행되므로
  `http://backend:8000`은 해석되지 않는다. `VITE_API_URL=http://localhost:8003/api/v1`이 정답이다.
  (반대로 백엔드→DB는 컨테이너 간 통신이므로 `POSTGRES_HOST=db`, 포트도 내부 포트 `5432`를 쓴다.)
- `VITE_API_URL`은 실행 시점에 주입되므로 값을 바꾸면 `docker compose up -d --force-recreate frontend`로 컨테이너를 다시 만들어야 한다.
  Vite는 `.env` 파일보다 **프로세스 환경변수를 우선**하므로, Docker에서는 compose가 주입한 값이 항상 이긴다.
- **CORS**: 브라우저가 보내는 Origin은 `http://localhost:8002`다. compose가 `CORS_ALLOWED_ORIGINS`로 주입하며,
  포트를 바꾸면 이 값도 같이 바꿔야 preflight(OPTIONS)가 통과한다.
- `backend` 컨테이너는 `db`의 healthcheck(`pg_isready`)가 통과한 뒤 시작하고,
  [entrypoint.sh](backend/entrypoint.sh)에서 `makemigrations` → `migrate`를 자동 수행한 뒤 runserver를 띄운다.
- `./backend`, `./frontend`가 바인드 마운트되어 있어 코드를 고치면 각각 StatReloader / Vite HMR로 즉시 반영된다.
  단 `requirements.txt`나 `package.json`을 바꾸면 이미지 재빌드(`docker compose up -d --build`)가 필요하다.

## 실행 (Docker 없이 로컬)

### Backend

```bash
cd backend
python -m venv .venv && .venv\Scriptsctivate     # Windows
pip install -r requirements.txt
# 로컬 PostgreSQL 접속 정보를 환경변수로 지정 (기본값: pinroute/pinroute@127.0.0.1:5432)
python manage.py migrate
python manage.py runserver
python manage.py test trips
```

### Frontend

```bash
cp .env.example .env                 # 루트에 한 번만 (Docker와 공용)
cd frontend
npm install
npm run dev                          # http://localhost:8002/onboarding
```

`.env`는 **프로젝트 루트 하나**만 둔다. compose가 읽는 파일과 동일한 파일을
Vite도 읽도록 [vite.config.ts](frontend/vite.config.ts)에 `envDir: ".."`를 지정해 두었다.
Vite는 `VITE_` 접두사가 붙은 값만 번들에 노출하므로 같은 파일에 있는 `POSTGRES_PASSWORD` 등은 클라이언트로 새지 않는다.

## 남은 작업 (MVP 이후)

- 인증 도입: 현재 뷰는 `AllowAny`이며 `Trip`에 소유자(FK)가 없다. 사용자 모델 연결 후 `IsAuthenticated` + 소유자 필터링 필요.
- Step 1 도시 검색을 하드코딩된 인기 도시 목록 대신 실제 지오코딩 API로 교체.
- `flight_info`는 형태만 검증하며 실제 항공편 조회는 연동하지 않는다.
