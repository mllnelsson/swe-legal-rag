import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_ORIGIN = "http://localhost:8000";

// The app talks to the API over same-origin relative URLs so that
// `/api/documents/{id}/pdf` can be dropped straight into an iframe. In dev that
// means proxying rather than pointing at :8000 directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_ORIGIN, changeOrigin: true },
    },
  },
});
