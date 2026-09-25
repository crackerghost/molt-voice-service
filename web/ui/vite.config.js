import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "dist" },
  server: {
    port: 5173,
    // In dev the React app on :5173 reaches the FastAPI backend on :8000
    // through these proxies (the app uses location.host for WS/API calls).
    proxy: {
      "/ws": { target: "http://127.0.0.1:8000", ws: true },
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
