import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // .env를 프로젝트 루트(pin-route/.env) 하나로 통일한다.
  // Docker에서는 compose가 VITE_API_URL을 직접 주입하므로 이 설정과 무관하게 동작한다.
  envDir: "..",
  server: {
    // 0.0.0.0 바인딩이어야 컨테이너 밖 브라우저에서 접속된다.
    host: true,
    port: 8002,
    strictPort: true,
    // 바인드 마운트에서는 파일 변경 이벤트가 전달되지 않는 경우가 있어 폴링을 켠다.
    watch: { usePolling: true },
  },
});
