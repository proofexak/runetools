/**
 * Start / stop the bot container and its manual mode from the web app (PRO-90).
 *
 *  - The container: through the docker allowlist proxy (src/docker-proxy.ts) — inspect,
 *    start, stop of the one configured container, nothing else. Stop never removes it,
 *    so Start can always wake the same container again.
 *  - Manual mode inside it: lib/manual.py (the container's main process when BOT is unset)
 *    reports every 2 s in data/manual_status.json and acts on data/manual_request.json —
 *    the same data/ hand-over as the active account and "Take control".
 *
 * Start: container stopped → start it → wait for manual mode's first fresh report →
 * ask it to start what's missing (RuneLite, then the bot menu) → wait for its answer.
 * A container in unattended mode (BOT set) is only started: lib.headless does the rest.
 * One start / stop at a time; progress goes out on the bus ({type: "bot"}).
 */
import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import type { BotStatus, ContainerState } from "@runetools/shared";
import { writeDataFile } from "./accounts.js";
import type { Bus } from "./bus.js";
import { HttpError } from "./http.js";

/** manual_status.json older than this = manual mode isn't running (it writes every 2 s). */
export const MANUAL_FRESH_MS = 10_000;
export const WAIT_CONTAINER_MS = 30_000;
export const WAIT_MANUAL_MS = 90_000;     // container boot: Xvfb, VNC, then lib.manual
export const WAIT_LAUNCH_MS = 240_000;    // RuneLite's window may take 2 min (lib/manual WINDOW_TIMEOUT)
export const STOP_GRACE_S = 30;           // docker stop -t: the bot ends its session first
const POLL_MS = 1000;

type Job = NonNullable<BotStatus["job"]>;

interface ManualReport {
  ts: number; runelite: boolean; menu: boolean; phase: string; handled: string | null; error: string | null;
}

export interface BotControlOptions {
  proxyUrl: string | null;
  container: string;
  dataDir: string;
  bus?: Bus;
  fetch?: typeof fetch;
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  newId?: () => string;
}

export class BotControl {
  private job: Job | null = null;
  private busy = false;
  private readonly fetch: typeof fetch;
  private readonly now: () => number;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly newId: () => string;
  /** The background job in flight (tests await it). */
  running: Promise<void> | null = null;

  constructor(private o: BotControlOptions) {
    this.fetch = o.fetch ?? fetch;
    this.now = o.now ?? Date.now;
    this.sleep = o.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.newId = o.newId ?? randomUUID;
  }

  get enabled() { return this.o.proxyUrl !== null; }

  private url(action: "json" | "start" | "stop") {
    const q = action === "stop" ? `?t=${STOP_GRACE_S}` : "";
    return `${this.o.proxyUrl}/containers/${encodeURIComponent(this.o.container)}/${action}${q}`;
  }

  /** The container's state and its BOT (unattended mode) via the proxy. */
  async container(): Promise<{ state: ContainerState; bot: string | null }> {
    if (!this.o.proxyUrl) return { state: "unknown", bot: null };
    try {
      const res = await this.fetch(this.url("json"), { signal: AbortSignal.timeout(5000) });
      if (res.status === 404) return { state: "missing", bot: null };
      if (!res.ok) return { state: "unknown", bot: null };
      const info = (await res.json()) as { State?: { Running?: boolean }; Config?: { Env?: string[] } };
      const bot = (info.Config?.Env ?? []).find((e) => e.startsWith("BOT="))?.slice(4) || null;
      return { state: info.State?.Running ? "running" : "stopped", bot };
    } catch {
      return { state: "unknown", bot: null };
    }
  }

  /** lib/manual.py's last report, if fresh. */
  async manualReport(): Promise<ManualReport | null> {
    try {
      const raw = JSON.parse(await fs.readFile(path.join(this.o.dataDir, "manual_status.json"), "utf8")) as
        Partial<ManualReport>;
      if (typeof raw.ts !== "number" || this.now() - raw.ts * 1000 > MANUAL_FRESH_MS) return null;
      return {
        ts: raw.ts, runelite: raw.runelite === true, menu: raw.menu === true, phase: String(raw.phase ?? "idle"),
        handled: raw.handled == null ? null : String(raw.handled), error: raw.error == null ? null : String(raw.error),
      };
    } catch {
      return null;
    }
  }

  async status(): Promise<BotStatus> {
    const [c, report] = await Promise.all([this.container(), this.manualReport()]);
    const running = c.state === "running";
    return {
      enabled: this.enabled,
      container: c.state,
      mode: running ? (c.bot ? "unattended" : "manual") : null,
      bot: running ? c.bot : null,
      manual: running && report
        ? { runelite: report.runelite, menu: report.menu, phase: report.phase, error: report.error }
        : null,
      job: this.job ? { ...this.job } : null,
    };
  }

  start() { this.launch("start", () => this.doStart()); }
  stop() { this.launch("stop", () => this.doStop()); }

  private launch(action: Job["action"], body: () => Promise<void>) {
    if (!this.enabled) throw new HttpError(503, "bot control isn't set up (DOCKER_PROXY_URL)");
    if (this.busy) throw new HttpError(409, `a ${this.job?.action ?? "bot"} is already in progress`);
    this.busy = true;
    this.job = { action, phase: "checking", error: null, done: false };
    this.emit();
    this.running = body()
      .catch((err: Error) => { this.job = { ...this.job!, error: err.message, phase: "failed" }; })
      .finally(() => {
        this.job = { ...this.job!, done: true };
        if (!this.job.error) this.job.phase = "done";
        this.busy = false;
        this.emit();
      });
  }

  private phase(phase: string) {
    if (this.job?.phase === phase) return;
    this.job = { ...this.job!, phase };
    this.emit();
  }

  private emit() { this.o.bus?.emit({ type: "bot" }); }

  private async until<T>(what: string, timeoutMs: number, probe: () => Promise<T | null | undefined | false>): Promise<T> {
    const deadline = this.now() + timeoutMs;
    for (;;) {
      const value = await probe();
      if (value) return value;
      if (this.now() >= deadline) throw new Error(`timed out waiting for ${what}`);
      await this.sleep(POLL_MS);
    }
  }

  private async post(action: "start" | "stop") {
    const res = await this.fetch(this.url(action), {
      method: "POST", signal: AbortSignal.timeout((STOP_GRACE_S + 30) * 1000),
    });
    // 204 done, 304 already in that state
    if (res.status !== 204 && res.status !== 304) {
      const body = await res.text().catch(() => "");
      throw new Error(`docker ${action} failed (${res.status}) ${body}`.trim());
    }
  }

  private async doStart() {
    const c = await this.container();
    if (c.state === "missing") {
      throw new Error("the bot container doesn't exist — run `docker compose -f docker/docker-compose.yml up -d` once");
    }
    if (c.state === "unknown") throw new Error("can't reach Docker (docker proxy)");
    let bot = c.bot;
    if (c.state === "stopped") {
      this.phase("starting_container");
      await this.post("start");
      bot = (await this.until("the container", WAIT_CONTAINER_MS, async () => {
        const now = await this.container();
        return now.state === "running" ? now : null;
      })).bot;
    }
    if (bot) return;                                   // unattended: lib.headless takes it from here

    this.phase("waiting_for_manual");
    const first = await this.until("manual mode (lib.manual) in the container", WAIT_MANUAL_MS,
      () => this.manualReport());
    if (first.runelite && first.menu) return;          // nothing missing

    const id = this.newId();
    await writeDataFile(this.o.dataDir, "manual_request.json", `${JSON.stringify({ id, action: "start" })}\n`);
    const answer = await this.until("RuneLite and the bot menu", WAIT_LAUNCH_MS, async () => {
      const report = await this.manualReport();
      if (report?.phase && report.phase !== "idle") this.phase(report.phase);    // starting_runelite / _menu
      return report && report.handled === id ? report : null;
    });
    if (answer.error) throw new Error(answer.error);
  }

  private async doStop() {
    const c = await this.container();
    if (c.state === "unknown") throw new Error("can't reach Docker (docker proxy)");
    if (c.state !== "running") return;
    this.phase("stopping_container");
    await this.post("stop");
  }
}
