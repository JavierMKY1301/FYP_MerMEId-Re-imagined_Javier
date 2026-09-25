import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: the portal calls /api/* and Vite forwards to FastAPI on :8000.
// This avoids CORS configuration during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true, rewrite: p => p.replace(/^\/api/, "") } }
  }
});
