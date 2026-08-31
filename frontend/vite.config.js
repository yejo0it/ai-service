import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Docker Desktop(Windows) 바인드 마운트 위에서 dev 서버를 안정적으로 유지하기 위한 설정.
//
// 증상: 브라우저 흰 화면 + "React is not defined"
// 경로: 폴링 감시가 마운트를 stat 하다 EIO를 내거나 vite.config.js 변경을 오탐 ->
//       dev 서버 재시작 -> 재시작한 서버가 entry(index.html)를 못 찾아
//       "Skipping dependency pre-bundling" 상태로 뜨고, JSX가 plugin-react의
//       automatic runtime 대신 esbuild classic 변환(React.createElement)으로 나감 ->
//       main.jsx에 `import React`가 없으므로 브라우저에서 ReferenceError -> 흰 화면.
//
// 따라서 (1) 재시작해도 root/entry/cacheDir이 흔들리지 않게 못박고,
//        (2) 감시 대상에서 캐시/산출물을 빼서 재시작 루프를 끊는다.
const projectRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],

  // 재시작 후에도 루트 추정이 흔들리지 않도록 절대경로로 고정한다.
  root: projectRoot,

  // .env를 프로젝트 루트(pin-route/.env) 하나로 통일한다.
  // Docker에서는 compose가 VITE_API_URL을 직접 주입하므로 이 설정과 무관하게 동작한다.
  envDir: "..",

  // 기본값과 같은 위치지만 명시해 둔다. 비워두면 패키지 탐색이 실패한 재시작에서
  // <root>/.vite 로 떨어지는데, 그 디렉터리는 watch 대상이라 쓰기->감지->재시작 루프가 된다.
  cacheDir: "node_modules/.vite",

  // "Could not auto-determine entry point" 이후 사전 번들링이 통째로 스킵되는 것을 막는다.
  optimizeDeps: {
    entries: ["index.html"],
  },

  server: {
    // 0.0.0.0 바인딩이어야 컨테이너 밖 브라우저에서 접속된다.
    host: true,
    port: 8002,
    strictPort: true,
    // 바인드 마운트에서는 파일 변경 이벤트가 전달되지 않는 경우가 있어 폴링을 켠다.
    // 다만 간격을 늘리고 캐시/산출물을 제외해야 EIO와 재시작 오탐이 줄어든다.
    watch: {
      usePolling: true,
      interval: 300,
      binaryInterval: 1000,
      ignored: [
        "**/node_modules/**",
        "**/.git/**",
        "**/dist/**",
        "**/.vite/**",
      ],
    },
    // 호스트 포트와 컨테이너 포트가 같아야 HMR 소켓이 붙는다(8002:8002).
    hmr: { clientPort: 8002 },
  },
});
