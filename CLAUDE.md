# PinRoute Development Guidelines

이 문서는 PinRoute 프로젝트에서 Claude Code가 모든 개발 작업 시 준수해야 하는 공통 지침입니다.

## 1. Git 및 브랜치 관리

- 작업 시작 전 현재 브랜치와 Git 상태를 확인합니다.
- 기존 미커밋 변경 사항은 임의로 삭제하거나 덮어쓰지 않습니다.
- 새로운 작업은 develop 브랜치를 최신화한 후, develop에서 파생된 feature 브랜치에서 진행합니다.
- 브랜치명은 `feature/기능명` 형식을 사용합니다. 기존처럼 이슈 번호를 붙이거나(`feature/49-...`) 수정 작업에 `fix/*`를 쓰는 것도 허용합니다.
- 이미 해당 작업을 위한 feature 브랜치가 있다면 중복 생성하지 않습니다.
- main, develop 브랜치에서 직접 개발하지 않습니다.
- 작업 완료 후 PR을 통해 develop 브랜치에 병합하는 흐름을 따릅니다.
- feature/fix 브랜치는 main에 직접 PR하지 않습니다. develop에 병합한 뒤, 별도로 develop → main PR을 만들어 병합합니다.
- 병합은 머지 커밋(`gh pr merge --merge`)을 쓰고, develop·main은 병합 후에도 삭제하지 않습니다. 작업 브랜치 삭제 여부는 사용자에게 확인합니다.
- 사용자 승인 없이 commit, push, merge, rebase 또는 PR 생성 작업을 진행하지 않습니다.
- Git 충돌이나 기존 변경 사항으로 인해 안전한 진행이 어려운 경우 사용자에게 먼저 확인합니다.

## 2. 커밋 규칙

- 커밋은 반드시 사용자 승인 후 진행합니다.
- 커밋 메시지는 한국어로 작성하며 긍정형 표현을 사용합니다.
- 기존 프로젝트의 커밋 메시지 형식이 있다면 이를 따릅니다.
- 하나의 커밋에는 논리적으로 연관된 변경 사항만 포함합니다.

## 3. 코드 설계 및 구현

- 작업 전 기존 프로젝트 구조와 관련 코드를 분석합니다.
- 기존 아키텍처, 코딩 컨벤션 및 네이밍 규칙을 준수합니다.
- 기존 컴포넌트, 함수, 유틸리티를 최대한 재사용합니다.
- 중복 코드를 최소화하고 유지보수성을 고려하여 구현합니다.
- 불필요한 추상화, 새로운 라이브러리 도입 및 과도한 리팩터링을 지양합니다.
- 요청된 기능에 필요한 최소 범위만 수정합니다.

## 4. UI 및 기능 변경

- 기존 UI 디자인과 사용자 경험을 최대한 유지합니다.
- UI 변경 요구사항이 모호하거나 여러 구현 방식이 가능한 경우 작업 전 사용자에게 확인합니다.
- 요청하지 않은 디자인 변경이나 기능 추가를 임의로 진행하지 않습니다.
- 기존 API, DB, 인증 기능과의 호환성을 고려합니다.
- 환경변수, API Key 등 민감정보를 코드에 하드코딩하지 않습니다.

## 5. 테스트 및 검증

- 구현 완료 후 변경 사항에 적합한 테스트를 수행합니다.
- 기존 기능에 영향을 주는 변경이라면 관련 회귀 테스트도 수행합니다.
- 필요한 경우 빌드, 타입 검사, 린트 등을 실행합니다.
- 테스트를 실행하지 못했거나 실패한 경우 이유를 명확히 보고합니다.
- 실제 수행하지 않은 테스트를 성공했다고 보고하지 않습니다.

## 6. 작업 결과 보고

모든 답변과 작업 결과는 한국어로 작성합니다.

작업 완료 후 다음 내용을 간결하게 보고합니다.

1. **작업 브랜치:** 브랜치명
2. **변경 파일:** 주요 수정 파일
3. **구현 내용:** 변경 사항 요약
4. **검증 결과:** 수행한 테스트 및 결과
5. **특이사항:** 미해결 문제 또는 추가 확인 사항

## 7. 작업 완료 원칙

- 요청한 요구사항을 충족했는지 확인합니다.
- 관련 없는 파일은 수정하지 않습니다.
- 사용자 승인 없이 커밋하거나 원격 저장소에 반영하지 않습니다.
- 작업 완료 후 feature 브랜치를 유지하고 사용자에게 결과를 보고합니다.

---

## 참고: 프로젝트 정보

### 개요와 기술 스택

PinRoute(핀루트)는 여행지·항공권·숙소를 등록하고 캘린더로 일정을 관리하는 여행 계획 서비스입니다.

| 구분 | 기술 |
| --- | --- |
| Frontend | React 18 · TypeScript · Vite · Tailwind CSS 4 · React Router |
| Backend | Python 3.11 · Django 5 · Django REST Framework (Token 인증) |
| Database | PostgreSQL 16 (+ pgvector) |
| Infra | Docker Compose |

### 구조

- `backend/accounts`: 회원·로그인·소셜 로그인·마이페이지(닉네임, 사진, 이메일, 비밀번호, 탈퇴)
- `backend/trips`: 여행·일정·숙소·짐싸기 노트·일행 초대·AI 일정 제안
- `backend/guides`: 여행 정보 검색(RAG) 문서 수집·검색
- `backend/config`: Django 설정
- `frontend/src`: `auth`, `home`, `trips`, `packing`, `mypage`, `onboarding`, `components/layout`(공통 레이아웃·페이지 너비), `api/client.ts`, `types/api.ts`

### 실행과 테스트

`.env`는 `.env.example`을 복사해 필요한 키만 채웁니다.

```bash
docker compose up -d --build                                   # 웹 :8002, API :8003, DB :5433
docker compose exec -T backend python manage.py test            # 백엔드 테스트
docker compose exec -T backend python manage.py migrate         # 새 마이그레이션 적용
docker compose exec -T frontend npx tsc -b --noEmit             # 프런트엔드 타입 검사
```

- 타입 검사 후 생기는 `frontend/tsconfig.tsbuildinfo`는 커밋하지 않습니다.
- 여행 정보 검색 문서는 필요할 때만 `docker compose exec backend python manage.py ingest_guides`로 수집합니다.

### 개발 중 참고

- 개발 서버에서 `auth/me`·`trips` API가 1분마다 반복되면 앱 코드의 루프가 아니라, PC 절전 후 Vite WebSocket이 끊겨 페이지가 전체 새로고침되는 것일 수 있습니다. 브라우저 콘솔의 `[vite] server connection lost` 메시지를 먼저 확인합니다.
