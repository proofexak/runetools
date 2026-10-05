import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const API = process.env.API_URL || "http://127.0.0.1:8778";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: API,
        changeOrigin: true,          // the API checks Host
        ws: true,                    // the live view's VNC stream (/api/live/vnc)
        configure: (proxy) => {
          // the browser's Origin is the dev server; the API only accepts its own
          proxy.on("proxyReq", (req) => req.removeHeader("origin"));
          proxy.on("proxyReqWs", (req) => req.removeHeader("origin"));
        },
      },
    },
  },
  test: { include: ["src/**/*.test.ts"] },
});
