import type { BotStatus } from "@runetools/shared";
import { describe, expect, it } from "vitest";
import { botView } from "./bot-control";

const base: BotStatus = { enabled: true, container: "stopped", mode: null, bot: null, manual: null, job: null };
const up = (runelite: boolean, menu: boolean): BotStatus =>
  ({ ...base, container: "running", mode: "manual", manual: { runelite, menu, phase: "idle", error: null } });

describe("botView", () => {
  it("stopped: Start, no Stop", () => {
    expect(botView(base)).toMatchObject({ tone: "off", canStart: true, canStop: false, watchable: false });
  });

  it("manual mode with something missing: Start launches it; RuneLite up is already watchable", () => {
    expect(botView(up(false, false))).toMatchObject({ canStart: true, canStop: true, watchable: false });
    expect(botView(up(true, false))).toMatchObject({ canStart: true, watchable: true,
      headline: "RuneLite or the bot menu isn't running" });
  });

  it("ready: nothing to start, Stop and Watch live", () => {
    const v = botView(up(true, true));
    expect(v).toMatchObject({ tone: "ready", canStart: false, canStop: true, watchable: true });
    expect(v.rows.map((r) => [r.label, r.value])).toEqual([
      ["Container", "running"], ["RuneLite", "running"], ["Bot menu", "running"]]);
  });

  it("unattended: running is ready, nothing to start", () => {
    const v = botView({ ...base, container: "running", mode: "unattended", bot: "Tanning" });
    expect(v).toMatchObject({ tone: "ready", canStart: false, canStop: true, watchable: true,
      headline: "Running unattended: Tanning" });
  });

  it("while a start / stop runs: its phase, no buttons", () => {
    const v = botView({ ...base, job: { action: "start", phase: "starting_runelite", error: null, done: false } });
    expect(v).toMatchObject({ tone: "busy", headline: "Starting RuneLite…", canStart: false, canStop: false });
  });

  it("a failed start shows its error and can be tried again", () => {
    const v = botView({ ...base, job: { action: "start", phase: "failed", error: "can't reach Docker", done: true } });
    expect(v).toMatchObject({ error: "can't reach Docker", canStart: true });
  });

  it("missing / unknown / manual mode silent are problems with no Start", () => {
    expect(botView({ ...base, container: "missing" })).toMatchObject({ tone: "problem", canStart: false, canStop: false });
    expect(botView({ ...base, container: "unknown" })).toMatchObject({ tone: "problem", canStart: false });
    expect(botView({ ...base, container: "running", mode: "manual" }))
      .toMatchObject({ tone: "problem", headline: "Manual mode isn't answering", canStart: false, canStop: true });
  });
});
