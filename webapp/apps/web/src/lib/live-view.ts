import type { LiveControl } from "@runetools/shared";

/** The bot answers a request within a poll (~0.25 s); silence this long = no bot is running. */
export const NO_ANSWER_MS = 3000;

/**
 * Where "Take control" stands:
 * - released: view-only, the bot has the game
 * - pausing:  asked; the bot hasn't reached its pause yet (a step is still running)
 * - control:  the bot is parked in its pause; mouse and keyboard are the human's
 * - no-bot:   nobody answered: no bot is running, so nothing can fight the human for the mouse
 */
export type ControlPhase = "released" | "pausing" | "control" | "no-bot";

export function controlPhase(c: LiveControl | undefined, now: number): ControlPhase {
  if (!c?.held) return "released";
  if (c.bot?.held && c.bot.safe) return "control";
  if (c.bot === null && c.requestedAt !== null && now - Date.parse(c.requestedAt) >= NO_ANSWER_MS) return "no-bot";
  return "pausing";
}

export const isInteractive = (phase: ControlPhase) => phase === "control" || phase === "no-bot";

/** The VNC WebSocket on this page's own origin (the API bridges it to x11vnc). */
export function vncUrl(loc: Pick<Location, "protocol" | "host"> = window.location) {
  return `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}/api/live/vnc`;
}
