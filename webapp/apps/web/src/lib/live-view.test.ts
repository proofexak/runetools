import type { LiveControl } from "@runetools/shared";
import { describe, expect, it } from "vitest";
import { controlPhase, isInteractive, NO_ANSWER_MS, vncUrl } from "./live-view";

const at = "2026-10-05T10:00:00.000Z";
const t0 = Date.parse(at);
const held = (bot: LiveControl["bot"]): LiveControl => ({ held: true, id: "r1", requestedAt: at, bot });

describe("controlPhase", () => {
  it("is released with no request or a release", () => {
    expect(controlPhase(undefined, t0)).toBe("released");
    expect(controlPhase({ held: false, id: "r2", requestedAt: at, bot: { held: false, safe: true } }, t0)).toBe("released");
  });

  it("waits for the bot to park in its pause", () => {
    expect(controlPhase(held(null), t0 + 100)).toBe("pausing");
    expect(controlPhase(held({ held: true, safe: false }), t0 + 60_000)).toBe("pausing");
    expect(controlPhase(held({ held: true, safe: true }), t0 + 100)).toBe("control");
  });

  it("hands over when no bot answers at all", () => {
    expect(controlPhase(held(null), t0 + NO_ANSWER_MS - 1)).toBe("pausing");
    expect(controlPhase(held(null), t0 + NO_ANSWER_MS)).toBe("no-bot");
  });

  it("only control and no-bot make the viewer interactive", () => {
    expect(["released", "pausing", "control", "no-bot"].map((p) => isInteractive(p as never))).toEqual([false, false, true, true]);
  });
});

describe("vncUrl", () => {
  it("uses the page's own origin", () => {
    expect(vncUrl({ protocol: "http:", host: "127.0.0.1:8778" })).toBe("ws://127.0.0.1:8778/api/live/vnc");
    expect(vncUrl({ protocol: "https:", host: "bots.local" })).toBe("wss://bots.local/api/live/vnc");
  });
});
