import os from "node:os";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// One server for the whole run (state carries over: setup → accounts → vault ...),
// so the specs run in order on one worker.
const PORT = 8791;
process.env.E2E_PORT = String(PORT);
process.env.E2E_ROOT ??= path.join(os.tmpdir(), "runetools-e2e");

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? "list" : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    permissions: ["clipboard-read", "clipboard-write"],
  },
  webServer: {
    command: "pnpm --filter @runetools/web build && node e2e/start-server.mjs",
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "pipe",
  },
});
