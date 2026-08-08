import path from "node:path"
import { defineConfig } from "vitest/config"

// Separate from vite.config.ts on purpose: vitest 3 bundles its own
// Vite (7.x), and its defineConfig types plugins against that copy,
// which collides with this project's Vite 8. The unit tests run
// through Vitest's esbuild transform — no react/tailwind plugins are
// needed here — so this config only carries the test environment and
// the same @/ alias as the app config.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
})
