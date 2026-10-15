import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Three pages, one build: the story page (landing.html), the app (app.html) and the 404 page (notfound.html).
// The output goes into the Python package (backend/web), where FastAPI serves it, so
// `pip install ckpoint` ships the UI and `chokepoint map` works offline.
// `npm run dev` proxies /api to a backend on :8000 (uvicorn chokepoint.api.app:app).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: resolve(import.meta.dirname, "../backend/web"),
    emptyOutDir: true,
    // the graph libraries (Cytoscape + layouts) are one ~600 kB chunk, loaded only by the app
    chunkSizeWarningLimit: 700,
    rolldownOptions: {
      input: {
        landing: resolve(import.meta.dirname, "landing.html"),
        app: resolve(import.meta.dirname, "app.html"),
        notfound: resolve(import.meta.dirname, "notfound.html"),
      },
      output: {
        // Stable, readable chunks: libraries change rarely, so browsers keep them cached.
        codeSplitting: {
          groups: [
            { name: "graph", test: /node_modules[\\/](cytoscape|cytoscape-dagre|cytoscape-fcose|cose-base|layout-base|@dagrejs|dagre)[\\/]/, priority: 3 },
            { name: "vendor", test: /node_modules[\\/](react|react-dom|scheduler|gsap|@gsap)[\\/]/, priority: 2 },
            // shared by both pages: our helpers, icons, base styles and fonts (never a page's own CSS)
            { name: "shared", test: /[\\/]src[\\/](lib|components)[\\/]|[\\/]src[\\/]styles[\\/](base\.css|fonts\.ts)|node_modules[\\/]@fontsource/, priority: 1 },
          ],
        },
      },
    },
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  // Unit tests for the pure logic in src/; the browser tests (e2e/) run with Playwright.
  test: { include: ["src/**/*.test.ts"] },
});
