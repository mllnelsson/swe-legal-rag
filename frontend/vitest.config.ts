import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The label-parity test imports the backend's `_dtos.py` as raw text to check
  // that the client has Swedish words for every progress key the API can emit.
  // That file lives outside `frontend/`, which Vite refuses to serve by default.
  // Test-runner config only — `vite.config.ts` is untouched, so the dev server's
  // file access is unchanged.
  server: { fs: { allow: [".."] } },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
