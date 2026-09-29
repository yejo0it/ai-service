/// <reference types="vite/client" />

/** 프론트에서 쓰는 환경 변수 (docker-compose의 frontend.environment 또는 루트 .env) */
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_KAKAO_REST_API_KEY?: string;
  readonly VITE_NAVER_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
