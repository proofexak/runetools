/** Bot container start / stop + manual mode (PRO-90): the docker proxy, BotControl, the routes. */
import fs from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BotControl, MANUAL_FRESH_MS } from "../src/bot-control.js";
import { allowRequest, createDockerProxy } from "../src/docker-proxy.js";
import { HOST, login, makeApp, tmpDir, type TestApp } from "./helpers.js";

const NAME = "runetools-runetools-1";

// ── docker proxy ─────────────────────────────────────────────────────────────

describe("docker proxy allowlist", () => {
  it.each([
    ["GET", `/containers/${NAME}/json`],
    ["GET", `/v1.47/containers/${NAME}/json`],
    ["POST", `/containers/${NAME}/start`],
    ["POST", `/containers/${NAME}/stop`],
    ["POST", `/v1.47/containers/${NAME}/stop?t=30`],
  ])("lets %s %s through", (method, url) => {
    expect(allowRequest(method, url, NAME)).toBe(true);
  });

  it.each([
    ["POST", `/containers/${NAME}/json`],                     // wrong method
    ["GET", `/containers/${NAME}/start`],
    ["DELETE", `/containers/${NAME}`],                        // remove
    ["POST", `/containers/${NAME}/exec`],                     // exec = a shell in the container
    ["POST", `/containers/${NAME}/kill`],
    ["POST", "/containers/create"],                           // create = root on the host
    ["GET", "/containers/json"],                              // list everything
    ["GET", "/containers/other/json"],                        // another container
    ["POST", "/containers/runetools-webapp-1/stop"],
    ["POST", `/containers/${NAME}/start?detachKeys=x`],       // extra parameters
    ["POST", `/containers/${NAME}/stop?t=30&signal=KILL`],
    ["POST", `/containers/${NAME}/stop?t=abc`],
    ["GET", `/containers/${NAME}/../other/json`],
    ["GET", `/containers/${encodeURIComponent(NAME + "/x")}/json`],
    ["GET", "/images/json"],
    ["POST", "/v1.47/build"],
  ])("refuses %s %s", (method, url) => {
    expect(allowRequest(method, url, NAME)).toBe(false);
  });
});

describe("docker proxy forwarding", () => {
  let upstream: http.Server, proxy: http.Server;
  afterEach(async () => {
    await Promise.all([upstream, proxy].map((s) => new Promise((r) => s?.close(r))));
  });

  it("forwards allowed calls to Docker and answers 403 to the rest without touching it", async () => {
    const seen: string[] = [];
    upstream = http.createServer((req, res) => {
      seen.push(`${req.method} ${req.url}`);
      res.writeHead(204).end();
    }).listen(0, "127.0.0.1");
    await new Promise((r) => upstream.once("listening", r));
    proxy = createDockerProxy({ container: NAME, upstream: { host: "127.0.0.1", port: (upstream.address() as AddressInfo).port } })
      .listen(0, "127.0.0.1");
    await new Promise((r) => proxy.once("listening", r));
    const base = `http://127.0.0.1:${(proxy.address() as AddressInfo).port}`;

    expect((await fetch(`${base}/containers/${NAME}/start`, { method: "POST" })).status).toBe(204);
    const denied = await fetch(`${base}/containers/create`, { method: "POST", body: "{}" });
    expect(denied.status).toBe(403);
    expect(await denied.json()).toMatchObject({ message: expect.stringContaining("not allowed") });
    expect(seen).toEqual([`POST /containers/${NAME}/start`]);
  });
});

// ── BotControl against a fake Docker + a fake lib/manual.py ──────────────────

/** Docker (via the proxy) and the container's manual mode, on one fake clock. */
class FakeHost {
  now = 1_700_000_000_000;
  state: "running" | "stopped" | "missing" = "stopped";
  env = ["PATH=/x", "BOT="];
  bootMs = 3000;           // container start → lib.manual's first report
  launchMs = 5000;         // a start request → RuneLite + menu up
  manualUp = true;         // lib.manual runs in this container
  launchError: string | null = null;
  runelite = false;
  menu = false;
  startedAt = 0;
  requestAt = 0;
  calls: string[] = [];
  unreachable = false;

  constructor(public dataDir: string) {}

  fetch = (async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    this.calls.push(`${method} ${url.replace(/^http:\/\/proxy/, "")}`);
    if (this.unreachable) throw new TypeError("fetch failed");
    if (this.state === "missing") return new Response("{}", { status: 404 });
    if (url.endsWith("/json")) {
      return Response.json({ State: { Running: this.state === "running" }, Config: { Env: this.env } });
    }
    if (url.endsWith("/start")) {
      if (this.state === "running") return new Response(null, { status: 304 });
      this.state = "running";
      this.startedAt = this.now;
      return new Response(null, { status: 204 });
    }
    if (url.includes("/stop")) {
      if (this.state !== "running") return new Response(null, { status: 304 });
      this.state = "stopped";
      this.runelite = this.menu = false;
      return new Response(null, { status: 204 });
    }
    return new Response("{}", { status: 500 });
  }) as typeof fetch;

  /** Time passes: the container's lib.manual reports and acts on requests. */
  sleep = async (ms: number) => {
    this.now += ms;
    this.tick();
  };

  tick() {
    const file = path.join(this.dataDir, "manual_status.json");
    if (this.state !== "running" || !this.manualUp || this.env.includes("BOT=Tanning") ||
        this.now - this.startedAt < this.bootMs) return;
    let handled: string | null = null;
    let phase = "idle";
    const reqFile = path.join(this.dataDir, "manual_request.json");
    if (fs.existsSync(reqFile)) {
      const req = JSON.parse(fs.readFileSync(reqFile, "utf8")) as { id: string };
      this.requestAt ||= this.now;
      if (this.now - this.requestAt >= this.launchMs) {
        if (!this.launchError) this.runelite = this.menu = true;
        handled = req.id;
      } else {
        phase = this.now - this.requestAt < this.launchMs / 2 ? "starting_runelite" : "starting_menu";
      }
    }
    fs.mkdirSync(this.dataDir, { recursive: true });
    fs.writeFileSync(file, JSON.stringify({
      pid: 1, ts: this.now / 1000, runelite: this.runelite, menu: this.menu, phase, handled,
      error: handled ? this.launchError : null,
    }));
  }
}

function control(host: FakeHost, proxyUrl: string | null = "http://proxy") {
  return new BotControl({
    proxyUrl, container: NAME, dataDir: host.dataDir, fetch: host.fetch,
    now: () => host.now, sleep: host.sleep, newId: () => "req-1",
  });
}

describe("BotControl", () => {
  it("wakes a stopped container, then starts RuneLite + the bot menu in manual mode", async () => {
    const host = new FakeHost(tmpDir());
    const c = control(host);
    expect(await c.status()).toMatchObject({ enabled: true, container: "stopped", mode: null, manual: null, job: null });

    c.start();
    await c.running;
    const s = await c.status();
    expect(s).toMatchObject({
      container: "running", mode: "manual", bot: null,
      manual: { runelite: true, menu: true, phase: "idle", error: null },
      job: { action: "start", phase: "done", error: null, done: true },
    });
    expect(host.calls.filter((x) => x.startsWith("POST"))).toEqual([`POST /containers/${NAME}/start`]);
    expect(JSON.parse(fs.readFileSync(path.join(host.dataDir, "manual_request.json"), "utf8")))
      .toEqual({ id: "req-1", action: "start" });
  });

  it("with everything already up it starts nothing", async () => {
    const host = new FakeHost(tmpDir());
    host.state = "running";
    host.runelite = host.menu = true;
    host.tick();
    const c = control(host);
    c.start();
    await c.running;
    expect((await c.status()).job).toMatchObject({ phase: "done", error: null });
    expect(host.calls.some((x) => x.startsWith("POST"))).toBe(false);
    expect(fs.existsSync(path.join(host.dataDir, "manual_request.json"))).toBe(false);
  });

  it("an unattended container (BOT set) is only started: lib.headless does the rest", async () => {
    const host = new FakeHost(tmpDir());
    host.env = ["BOT=Tanning"];
    const c = control(host);
    c.start();
    await c.running;
    const s = await c.status();
    expect(s).toMatchObject({ container: "running", mode: "unattended", bot: "Tanning", job: { phase: "done" } });
    expect(fs.existsSync(path.join(host.dataDir, "manual_request.json"))).toBe(false);
  });

  it.each([
    ["missing", (h: FakeHost) => { h.state = "missing"; }, "doesn't exist"],
    ["docker unreachable", (h: FakeHost) => { h.unreachable = true; }, "can't reach Docker"],
    ["manual mode never reports", (h: FakeHost) => { h.manualUp = false; }, "timed out waiting for manual mode"],
    ["RuneLite fails to start", (h: FakeHost) => { h.launchError = "TimeoutError: RuneLite's window didn't appear"; },
      "window didn't appear"],
  ])("reports a failed start: %s", async (_name, setup, message) => {
    const host = new FakeHost(tmpDir());
    setup(host);
    const c = control(host);
    c.start();
    await c.running;
    expect((await c.status()).job).toMatchObject({ action: "start", phase: "failed", done: true,
      error: expect.stringContaining(message) });
  });

  it("stops a running container (never removes it) and a stopped one is left alone", async () => {
    const host = new FakeHost(tmpDir());
    host.state = "running";
    const c = control(host);
    c.stop();
    await c.running;
    expect(host.calls).toContain(`POST /containers/${NAME}/stop?t=30`);
    expect(await c.status()).toMatchObject({ container: "stopped", job: { action: "stop", phase: "done" } });
    host.calls = [];
    c.stop();
    await c.running;
    expect(host.calls.some((x) => x.startsWith("POST"))).toBe(false);
  });

  it("one start / stop at a time; refuses when not set up", async () => {
    const host = new FakeHost(tmpDir());
    const c = control(host);
    c.start();
    expect(() => c.stop()).toThrow(/already in progress/);
    await c.running;
    expect(() => control(host, null).start()).toThrow(/isn't set up/);
  });

  it("a stale manual report counts as manual mode not running", async () => {
    const host = new FakeHost(tmpDir());
    host.state = "running";
    host.tick();
    const c = control(host);
    expect((await c.status()).manual).not.toBeNull();
    host.now += MANUAL_FRESH_MS + 1;
    expect((await c.status()).manual).toBeNull();
  });
});

// ── routes ───────────────────────────────────────────────────────────────────

describe("/api/bot", () => {
  let t: TestApp;
  afterEach(async () => {
    vi.unstubAllGlobals();
    await t?.close();
  });

  it("needs a login, and the CSRF token to start / stop", async () => {
    const host = new FakeHost(tmpDir());
    vi.stubGlobal("fetch", host.fetch);
    t = await makeApp({ dockerProxyUrl: "http://proxy", botContainer: NAME, dataDir: host.dataDir });
    expect((await t.app.inject({ url: "/api/bot", headers: { host: HOST } })).statusCode).toBe(401);
    const c = await login(t.app);
    const res = await c.get("/api/bot");
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ enabled: true, container: "stopped", job: null });

    const noCsrf = await t.app.inject({ method: "POST", url: "/api/bot/start", headers: { host: HOST },
      cookies: { rt_session: c.cookie } });
    expect(noCsrf.statusCode).toBe(403);
    expect(host.calls.some((x) => x.startsWith("POST"))).toBe(false);

    const started = await c.post("/api/bot/stop");
    expect(started.statusCode).toBe(202);
    expect(started.json().job).toMatchObject({ action: "stop" });
  });

  it("without DOCKER_PROXY_URL the panel is off and start is refused", async () => {
    t = await makeApp();
    const c = await login(t.app);
    expect((await c.get("/api/bot")).json()).toMatchObject({ enabled: false, container: "unknown" });
    expect((await c.post("/api/bot/start")).statusCode).toBe(503);
  });
});
