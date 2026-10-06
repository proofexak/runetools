// Starts the API for the e2e run: in-memory PGlite, generated session logs dated
// relative to now, a throwaway data dir, and the built UI (pnpm --filter @runetools/web build).
// Everything lives under E2E_ROOT (set by playwright.config.ts), wiped on every run.
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = process.env.E2E_ROOT;
fs.rmSync(root, { recursive: true, force: true });
const logs = path.join(root, "repo");
fs.mkdirSync(path.join(root, "data"), { recursive: true });

const p = (n, w = 2) => String(n).padStart(w, "0");
const wall = (d) => `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
const stamp = (d) => wall(d).slice(0, 19).replace(/[-:]/g, "").replace("T", "_");

function write(rel, bot, start, events) {
  const file = path.join(logs, rel, "log", `${bot}_${stamp(start)}.jsonl`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const lines = events.map(([offsetS, e]) => JSON.stringify({
    ts: wall(new Date(start.getTime() + offsetS * 1000)), session: stamp(start), bot, ...e,
  }));
  fs.writeFileSync(file, lines.join("\n") + "\n");
  return file;
}

const now = Date.now();
const hoursAgo = (h) => new Date(now - h * 3600_000);

// yesterday: a finished tanner session on Zezima, 2 h
write("tanner", "tanner", hoursAgo(26), [
  [0, { event: "session_start", params: { hide_type: "green dragonhide" }, pid: 1, account: "Zezima" }],
  [60, { event: "step", state: "walk_to_tanner", result: "ok", seconds: 15, run: 1 }],
  [120, { event: "step", state: "trade_ellis", result: "fail", seconds: 20, run: 1 }],
  [7200, { event: "session_end", final: "done", reason: "out of hides", last_step: "banking", stats: { run: 80 },
    active_seconds: 7200, paused_seconds: 0 }],
]);
// earlier today: a crash
write("tanner", "tanner", hoursAgo(3), [
  [0, { event: "session_start", params: {}, pid: 2, account: "Zezima" }],
  [30, { event: "step", state: "walk_to_tanner", result: "ok", seconds: 30, run: 1 }],
  [31, { event: "error", where: "session", state: "trade_ellis", type: "TimeoutError", message: "Ellis never answered",
    traceback: "Traceback (most recent call last):\n  File \"tanner/actions.py\", line 1, in trade_ellis\nTimeoutError: Ellis never answered\n" }],
  [32, { event: "session_end", final: "crashed", reason: null, last_step: "trade_ellis", stats: { run: 1 },
    active_seconds: 32, paused_seconds: 0 }],
]);
// running right now (fresh mtime, no session_end)
write("miner/golden_nuggets", "golden_nuggets", new Date(now - 20 * 60_000), [
  [0, { event: "session_start", params: {}, pid: 3 }],
  [300, { event: "step", state: "mine", result: "ok", seconds: 300, run: 1 }],
  [600, { event: "step", state: "deposit", result: "ok", seconds: 20, run: 2 }],
]);

// ── a stand-in bot container (PRO-90): the docker proxy + lib/manual.py's data/ files ──
// Docker: one container, stopped at first. Once running, "manual mode" reports in
// data/manual_status.json every 300 ms and answers a start request in ~2 s (RuneLite, then menu).
const container = "runetools-runetools-1";
const bot = { running: false, since: 0, runelite: false, menu: false, request: null, requestAt: 0, handled: null };
const proxy = http.createServer((req, res) => {
  const m = /^\/containers\/([^/]+)\/(json|start|stop)/.exec(req.url ?? "");
  if (!m || m[1] !== container) return res.writeHead(403).end("{}");
  if (m[2] === "json") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ State: { Running: bot.running }, Config: { Env: ["BOT="] } }));
  }
  const want = m[2] === "start";
  if (bot.running === want) return res.writeHead(304).end();
  Object.assign(bot, { running: want, since: Date.now(), runelite: false, menu: false });
  return res.writeHead(204).end();
});
proxy.listen(Number(process.env.E2E_PORT) + 1, "127.0.0.1");
const statusFile = path.join(root, "data", "manual_status.json");
setInterval(() => {
  if (!bot.running || Date.now() - bot.since < 800) return;
  let phase = "idle";
  try {
    const req = JSON.parse(fs.readFileSync(path.join(root, "data", "manual_request.json"), "utf8"));
    if (req.id !== bot.request && req.id !== bot.handled) Object.assign(bot, { request: req.id, requestAt: Date.now() });
  } catch { /* no request yet */ }
  if (bot.request) {
    const t = Date.now() - bot.requestAt;
    if (t > 1000) bot.runelite = true;
    if (t > 2000) Object.assign(bot, { menu: true, handled: bot.request, request: null });
    else phase = bot.runelite ? "starting_menu" : "starting_runelite";
  }
  fs.writeFileSync(statusFile, JSON.stringify({ pid: 1, ts: Date.now() / 1000, runelite: bot.runelite, menu: bot.menu,
    phase, handled: bot.handled, error: null }));
}, 300);

const server = spawn(process.execPath, ["--import", "tsx", path.join(here, "../apps/api/src/server.ts")], {
  stdio: "inherit",
  env: {
    ...process.env,
    PORT: process.env.E2E_PORT,
    DATABASE_URL: "pglite:memory",
    LOG_ROOTS: logs,
    DATA_DIR: path.join(root, "data"),
    WEB_DIST: path.join(here, "../apps/web/dist"),
    POLL_MS: "5000",                // slow tailer: what shows up within ~1 s came by push
    VNC_ADDR: "127.0.0.1:1",    // nothing listens: never the real bot container's VNC
    DOCKER_PROXY_URL: `http://127.0.0.1:${Number(process.env.E2E_PORT) + 1}`,   // the stand-in above
    BOT_CONTAINER: container,
    // every spec logs in again, all from 127.0.0.1: the login rate limit (10/min) isn't under test here
    PASSWORD_RATE_LIMIT: "100",
    LOG_LEVEL: "warn",
  },
});
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => server.kill(sig));
server.on("exit", (code) => process.exit(code ?? 0));
