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
| Infra | Docker Compose · VS Code Dev Container |
| 외부 API | Google Places API (New) · Open-Meteo · ExchangeRate-API · 카카오/네이버 로그인 |

## Key Features

### 🏠 홈 대시보드
- **대형 캘린더**: 여행 기간을 날짜 띠와 제목 뱃지로 표시, 겹치는 여행도 구분
- **여행 색상**: 여행마다 파스텔 톤 8색 중 원하는 색 선택
- **요약 카드**: 날짜나 여행을 누르면 일정·경로·항공권·숙소 요약
- **위젯**: D-Day 카운트다운 · 여행지 날씨(현재 + 7일 예보) · 환율 · 여행 경로 타임라인

### 🧭 여행 생성 위저드
1. **여행지**: 여러 도시를 이동 순서대로 추가·삭제 (검색 목록에서 선택)
2. **일정**: 항공권(항공사 자동완성 · 편명 · 출국/귀국 일시) 또는 날짜만 등록
3. **숙소**: Google Places로 숙소 검색, 도시별 배정, 숙박 기간이 겹치지 않게 선택 (건너뛰기 가능)

### 🧳 내 여행
- 여행 중 · 다가오는 여행 · 지난 여행으로 나눈 목록

### 🔐 회원
- 이메일 회원가입(중복 확인 · 휴대폰 인증) · 로그인 · 카카오/네이버 로그인
- 아이디 찾기 · 비밀번호 재설정 · 로그아웃
- 로그인이 필요한 화면 보호, 로그인 후 원래 가려던 화면으로 이동

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
| `GOOGLE_MAPS_API_KEY` | 여행 상세 지도 (브라우저용 Maps JavaScript API 키, HTTP 리퍼러 제한 권장) |
| `KAKAO_REST_API_KEY` · `KAKAO_CLIENT_SECRET` | 카카오 로그인 |
| `NAVER_CLIENT_ID` · `NAVER_CLIENT_SECRET` | 네이버 로그인 |

**자주 쓰는 명령어**

```bash
docker compose logs -f backend                             # 백엔드 로그
docker compose exec backend python manage.py test          # 백엔드 테스트
docker compose exec backend python manage.py createsuperuser
docker compose exec frontend npm run typecheck             # 프론트 타입 검사
docker compose down                                        # 종료 (데이터 유지)
```

## Notes

- **DB 데이터**는 `pgdata` 볼륨에 저장됩니다. `docker compose down -v`는 데이터까지 삭제하니 주의하세요.
- **`.env`를 바꾼 뒤**에는 `docker compose up -d --build`로 컨테이너를 다시 만들어야 반영됩니다.
- **Google Places API 키**: 개발 환경은 IP가 자주 바뀌므로 IP 제한 대신 **API 제한(Places API (New)만 허용)** 과 **일일 할당량 제한**으로 관리하세요.
- **에디터 타입 인식**: 패키지가 컨테이너 안에 있으므로 VS Code는 `Dev Containers: Reopen in Container` → **PinRoute Frontend**로 여는 것을 권장합니다.
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
