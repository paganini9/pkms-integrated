import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // BFF 만 호출한다. 지식서비스(8000)는 프론트에서 직접 부르지 않는다 (내부 구조 비노출).
    proxy: {
      "/api": { target: process.env.BFF_URL ?? "http://localhost:4000", changeOrigin: true },
    },
  },
});
