import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  base: '/app/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // Dev: the Vite dev server proxies every /api call to the
      // FastAPI process (quantmesh-workstation on 127.0.0.1:8765).
      // Production: FastAPI serves the compiled bundle itself and
      // the SPA calls the same origin — no proxy involved.
      "/api": "http://127.0.0.1:8765",
    },
  },
})
