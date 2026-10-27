<div align="center">

<img src="frontend/public/favicon.svg" width="72" alt="PinRoute 로고" />

# PinRoute (핀루트)

**핀만 찍으면, 경로는 알아서**

여행지·항공권·숙소를 한 번에 등록하고, 캘린더로 여행 일정을 한눈에 관리하는 여행 계획 서비스

</div>

## Overview

- **한 번에 끝내는 여행 등록**: 여러 도시, 항공편, 숙소를 3단계 위저드로 입력
- **한눈에 보는 일정**: 여행 기간을 색으로 구분한 대형 캘린더와 D-Day
- **떠나기 전 필요한 정보**: 여행지 날씨 예보와 현지 통화 환율을 홈에서 바로 확인
- **간편한 계정**: 이메일 가입(휴대폰 인증)과 카카오·네이버 로그인 지원

> 숙소를 기준으로 한 일별 동선 최적화는 개발 중입니다.

## Tech Stack

| 구분 | 기술 |
| --- | --- |
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS 4 · React Router |
| Backend | Python 3.11 · Django 5 · Django REST Framework (Token 인증) |
| Database | PostgreSQL 16 |
| Infra | Docker Compose |
| 외부 API | Google Places API (New) · Open-Meteo · ExchangeRate-API · 카카오/네이버 로그인 |

## Key Features

### 🏠 홈 대시보드
- **대형 캘린더**: 여행 기간을 날짜 띠와 제목 뱃지로 표시, 겹치는 여행도 구분
- **여행 색상**: 여행마다 파스텔 톤 8색 중 원하는 색 선택
- **요약 카드**: 날짜나 여행을 누르면 일정·경로·항공권·숙소 요약
- **위젯**: D-Day 카운트다운 · 여행지 날씨(현재 + 7일 예보) · 환율 · 체크리스트 진행률 · 여행 경로 타임라인

### 🧭 여행 생성 위저드
1. **여행지**: 여러 도시를 이동 순서대로 추가·삭제 (검색 목록에서 선택)
2. **일정**: 항공권(항공사 자동완성 · 편명 · 출국/귀국 일시) 또는 날짜만 등록
3. **숙소**: Google Places로 숙소 검색, 도시별 배정, 숙박 기간이 겹치지 않게 선택 (건너뛰기 가능)

### 🗺️ 여행 상세
- **일별 일정**: 항공편·숙소 카드를 바탕으로 장소를 추가하고 순서 변경, 메모·시간 수정
- **지도**: 하루 동선을 지도에서 확인
- **AI와 함께 만들기**: 대화로 일정 제안을 받아 미리 보고 적용 (Claude)
- **일행 초대**: 초대 링크로 일행과 함께 일정 편집

### 🎒 여행 체크리스트
- 해야 할 일(예약·연락·환전 등) · 필수 준비물 · 세면도구/화장품 · 의류 · 전자제품 · 상비약 · 기타로 나눈 체크리스트
- 분류마다 항목 직접 추가·삭제·체크, 완료 비율을 홈 위젯에 표시

### 🧳 내 여행
- 여행 중 · 다가오는 여행 · 지난 여행으로 나눈 목록

## Getting Started

**필요한 것**: [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
git clone https://github.com/yejo0it/ai-service.git
cd ai-service
cp .env.example .env          # 필요한 키만 채우기 (아래 표 참고)
docker compose up -d --build
```

| 서비스 | 주소 |
| --- | --- |
| 웹 | http://localhost:8002 |
| API | http://localhost:8003/api/v1/ |
| 관리자 | http://localhost:8003/admin/ |
| DB | `localhost:5433` (PostgreSQL) |

**`.env` 주요 키** (비워 두어도 실행되며, 해당 기능만 비활성화됩니다)

| 키 | 용도 |
| --- | --- |
| `GOOGLE_PLACES_API_KEY` | 숙소 검색 |
| `ANTHROPIC_API_KEY` | 여행 상세 'AI와 함께 만들기' (Claude) |
| `NAVITIME_RAPIDAPI_KEY` | 'AI와 함께 만들기'의 일본 대중교통 이동 시간 (NAVITIME Route, RapidAPI 무료 요금제 월 500건). 비우면 대중교통 시간은 표시하지 않습니다. |
| `GOOGLE_ROUTES_API_KEY` | 'AI와 함께 만들기'의 실제 이동 시간 계산 (Google Routes API, 유료·서버 전용). 비우면 직선거리 기준으로 동작하며, 지원 지역은 동아시아(일본·한국·대만·홍콩·마카오·몽골)입니다(`ROUTES_COUNTRIES`). |
| `GOOGLE_MAPS_API_KEY` | 여행 상세 지도 (브라우저용 Maps JavaScript API 키, HTTP 리퍼러 제한 권장) |
| `KAKAO_REST_API_KEY` · `KAKAO_CLIENT_SECRET` | 카카오 로그인 |
| `NAVER_CLIENT_ID` · `NAVER_CLIENT_SECRET` | 네이버 로그인 |

**DB 마이그레이션 (필수)**

DB 테이블은 마이그레이션으로 만들어집니다. 마이그레이션이 적용되지 않으면 API가 오류를 돌려주니 꼭 확인하세요.

- 컨테이너를 처음 띄우거나 다시 시작하면 백엔드가 시작하면서 자동으로 적용합니다.
- **컨테이너가 켜져 있는 상태에서 새 코드를 받았다면(`git pull`) 직접 실행해야 합니다.**

```bash
docker compose exec backend python manage.py migrate
```

**여행 정보 검색 문서 수집 (선택)**

'AI와 함께 만들기'가 여행 준비 질문에 근거 문서(Wikivoyage)를 붙여 답하게 하려면 문서를 한 번 수집합니다. 처음 실행할 때 임베딩 모델(약 0.5GB)을 내려받고 몇 분 걸립니다. 수집하지 않아도 AI 대화는 근거 없이 그대로 동작합니다.

```bash
docker compose exec backend python manage.py ingest_guides
```

**로그 확인**

백엔드 로그는 모두 컨테이너 표준 출력으로 나가며 `docker compose logs`로 봅니다.

```bash
docker compose logs -f --tail 100 backend                       # 실시간 확인
docker compose logs --since 1h backend | grep -E "WARNING|ERROR"  # 최근 1시간 경고·오류
docker compose logs backend | grep '"event":"ai_request"'       # AI 요청 사용량(JSON 한 줄)
```

| 로그 | 형식 | 내용 |
| --- | --- | --- |
| 앱·Django | `시각 수준 로거: 메시지` | 앱 로그(`DJANGO_LOG_LEVEL`, 기본 `INFO`), 4xx 경고, 5xx 오류와 traceback |
| 요청 줄 | `[시각] "요청" 상태 크기` | 개발 서버(runserver)의 요청 기록 |
| AI 사용량 | JSON 한 줄 | 'AI와 함께 만들기' 토큰·응답 시간(숫자만, `AI_USAGE_LOG_ENABLED`) |
| 번역하지 못한 역 이름 | 파일 | `backend/logs/untranslated_names.jsonl` (`python manage.py untranslated_names`) |

- 외부 라이브러리는 경고 이상만 남깁니다. 앱은 대화 내용·API 키·인증 토큰을 기록하지 않습니다.
- 앱·Django 로그와 요청 줄은 traceback까지 포함한 출력 전체에서 초대 링크 토큰, URL 쿼리의 인증 값, `Authorization` 값, API 키, `password`·`secret`·`api_key` 같은 키의 값, DB 제약 위반 메시지의 값, 이메일 주소를 `***`로 가립니다(`backend/config/log_masking.py`). 키·컬럼 이름과 예외 종류·파일·줄 번호는 남습니다.
- 휴대폰 인증번호는 로그에 남기지 않습니다(SMS 미연동 안내 한 줄만 남고, 개발 서버는 인증번호를 화면에 표시합니다).
- **가려지지 않는 출력**: 아래는 로그 설정을 거치지 않아 위의 가림이 적용되지 않습니다.
  - 개발용 메일 출력: `EMAIL_HOST`가 비어 있으면 이메일 변경 인증 메일 전문(받는 사람 이메일, 인증 링크 토큰 포함)이 백엔드 로그에 그대로 찍힙니다. 개발에서만 쓰고, 운영은 `EMAIL_HOST`가 없으면 메일을 보내지 않습니다(503).
  - 관리 명령(`python manage.py ...`)의 터미널 출력
- **운영 배포 시 주의**
  - `DJANGO_DEBUG=0`으로 실행합니다. `docker-compose.yml`의 기본값은 개발용 `1`이며, `DEBUG=1`이면 오류 화면에 요청 정보가 보이고 개발용 출력이 켜집니다.
  - 기본 실행 명령은 개발 서버(runserver)입니다. 운영에서 다른 WSGI 서버를 쓰면 그 서버의 접근 로그(요청 URL·쿼리)는 위의 가림이 적용되지 않으므로 따로 설정해야 합니다.
- 컨테이너 로그는 서비스마다 10MB 파일 3개까지 보존합니다(`docker-compose.yml`의 `x-logging`). 바꾼 설정은 `docker compose up -d`로 컨테이너를 다시 만들어야 반영됩니다.

## Notes

- **DB 데이터**는 `pgdata` 볼륨에 저장됩니다. `docker compose down -v`는 데이터까지 삭제하니 주의하세요.
- **`.env`를 바꾼 뒤**에는 `docker compose up -d --build`로 컨테이너를 다시 만들어야 반영됩니다.
- **Google Places API 키**: 개발 환경은 IP가 자주 바뀌므로 IP 제한 대신 **API 제한(Places API (New)만 허용)** 과 **일일 할당량 제한**으로 관리하세요.
- **에디터 타입 인식**: 앱은 컨테이너의 패키지로 실행됩니다. VS Code에서 타입을 인식하려면 호스트의 `frontend` 폴더에서 `npm install`을 한 번 실행하세요.
- **휴대폰 인증**: SMS 발송은 아직 연동되지 않았습니다. 개발 서버에서는 인증번호가 화면에 표시됩니다.

---

<details>
<summary>프로젝트 배경 (AI 과정)</summary>

### 과정 / 학습 목표

오픈소스 기반 AI 기술을 활용하여 **실제 배포 가능한 AI 데모 서비스를 1개 이상 완성**하는 것을 목표로 합니다.
이 저장소에는 과정을 진행하며 실습 코드, 프로젝트 진행 과정을 기록합니다.

**현재 위치**

* Claude Code, Codex 등 AI Coding Agent의 개념과 활용 사례를 알고 있는 단계
* Python/Django 기반 백엔드 개발 경험은 있지만, LLM 및 AI Agent 개발 경험은 부족한 상태

**개인 목표**

* Agent, Model, AI Platform 등을 활용한 **AI Agent의 전체 동작 흐름** 이해
* MCP, Prompt Engineering, RAG, Tool Calling 등 핵심 기술 학습
* 목적에 맞는 AI 스택과 오픈소스 도구를 선택하고 활용할 수 있는 역량 확보
* 실제 서비스 형태로 배포 가능한 AI 데모 프로젝트 1개 이상 완성
* 학습 과정과 시행착오를 GitHub에 꾸준히 기록하여 기술 포트폴리오 구축

### 관심 트랙

* 🥇 **추천 / 분류 (1순위)**: 사용자 데이터를 기반으로 개인화 추천 및 매칭 서비스를 구현하는 프로젝트에 가장 관심이 있습니다.
  백엔드 개발 경험을 살려 추천 로직과 AI 모델을 실제 서비스 형태로 연결하는 과정을 경험해 보고 싶습니다.
* 🥈 **문서 기반 RAG (2순위)**: RAG(Retrieval-Augmented Generation)를 활용한 문서 검색 및 질의응답 서비스에 관심이 있습니다.
  기업 문서, 사내 지식베이스, FAQ 등 실무에서 활용 가능한 서비스를 직접 구현하며 AI 서비스 아키텍처를 경험해 보고 싶습니다.

</details>
