import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Separate from vite.config.ts on purpose: tsconfig.app.json's `include` is
// scoped to `src` only, so keeping the test runner config (and the `tests/`
// tree it points at) out of vite.config.ts means `tsc -b && vite build`
// (the production build) never has to know tests exist.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    css: false,
  },
});
