import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Divisão de código por rota: cada página é carregada com `lazy()` em
// `src/app/rotas.tsx`, o que gera um chunk por rota (Req 19.2).
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy local para a API (`python scripts/dev_local.py`, porta 8000) durante o
    // desenvolvimento. `/midia` serve as imagens de `seed/midia` pelo mesmo servidor.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/midia": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
