import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies to a daemon on :8781 so the UI still only ever talks to the daemon API.
export default defineConfig({
  plugins: [react()],
  // create-torrent / parse-torrent import Node's `path`; give them a small browser version.
  resolve: { alias: { path: fileURLToPath(new URL("./src/lib/path-shim.ts", import.meta.url)) } },
  build: { outDir: "dist", sourcemap: false },
  server: { proxy: { "/api": "http://127.0.0.1:8781", "/stream": "http://127.0.0.1:8781" } },
});
