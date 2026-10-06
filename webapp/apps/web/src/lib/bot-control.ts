/** What the bot container panel shows and allows, from GET /api/bot (PRO-90). */
import type { BotStatus } from "@runetools/shared";

export interface BotView {
  /** One line on top: what's going on. */
  headline: string;
  tone: "ready" | "busy" | "off" | "problem";
  rows: { label: string; value: string; on: boolean }[];
  canStart: boolean;
  canStop: boolean;
  /** RuneLite (manual) or the unattended bot is up: there's something to watch. */
  watchable: boolean;
  error: string | null;
}

const PHASES: Record<string, string> = {
  checking: "Checking the container…",
  starting_container: "Starting the container…",
  waiting_for_manual: "Waiting for the container to come up…",
  starting_runelite: "Starting RuneLite…",
  starting_menu: "Starting the bot menu…",
  stopping_container: "Stopping the container — a running bot ends its session first…",
};

export function botView(s: BotStatus): BotView {
  const busy = !!s.job && !s.job.done;
  const running = s.container === "running";
  const manual = s.mode === "manual";
  const runelite = !!s.manual?.runelite;
  const menu = !!s.manual?.menu;
  const ready = running && (s.mode === "unattended" || (runelite && menu));

  const rows: BotView["rows"] = [{ label: "Container", value: s.container, on: running }];
  if (running && s.mode === "unattended") rows.push({ label: "Mode", value: `unattended (${s.bot})`, on: true });
  if (running && manual) {
    rows.push({ label: "RuneLite", value: s.manual ? (runelite ? "running" : "not running") : "…", on: runelite });
    rows.push({ label: "Bot menu", value: s.manual ? (menu ? "running" : "not running") : "…", on: menu });
  }

  let headline: string, tone: BotView["tone"];
  if (busy) {
    headline = PHASES[s.job!.phase] ?? `${s.job!.phase}…`;
    tone = "busy";
  } else if (s.container === "missing") {
    headline = "The bot container doesn't exist yet — run docker compose -f docker/docker-compose.yml up -d once";
    tone = "problem";
  } else if (s.container === "unknown") {
    headline = "Can't reach Docker";
    tone = "problem";
  } else if (!running) {
    headline = "The bot container is stopped";
    tone = "off";
  } else if (ready) {
    headline = s.mode === "unattended" ? `Running unattended: ${s.bot}` : "Ready — pick a bot in the live view";
    tone = "ready";
  } else if (manual && !s.manual) {
    headline = "Manual mode isn't answering";
    tone = "problem";
  } else {
    headline = "RuneLite or the bot menu isn't running";
    tone = "off";
  }

  const failed = s.job?.done && s.job.error ? s.job.error : null;
  return {
    headline, tone, rows,
    canStart: !busy && (s.container === "stopped" || (running && manual && !!s.manual && !ready)),
    canStop: !busy && running,
    watchable: running && (s.mode === "unattended" || runelite),
    error: failed ?? s.manual?.error ?? null,
  };
}
