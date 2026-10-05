import type { LiveSession, Overview } from "@runetools/shared";
import { describe, expect, it } from "vitest";
import { advanceOverview } from "./live";

const session = (over: Partial<LiveSession>): LiveSession => ({
  id: 1, stamp: "s", bot: "tanner", account: null, startedAt: "2026-10-05T12:00:00.000",
  endedAt: "2026-10-05T12:10:00.000", status: "running", reason: null, lastStep: "walk", activeSeconds: 600,
  pausedSeconds: 0, runs: 3, errors: 0, idleSeconds: 2, state: "banking", stateSeconds: 30, paused: false, ...over,
});

const overview = (live: LiveSession[]): Overview => ({
  now: "2026-10-05T12:10:00.000",
  today: { hours: 1, runs: 3, sessions: 1, bots: { tanner: 1 } },
  week: { hours: 5, runs: 10, crashes: 0 },
  totalHours: 50,
  daily: [],
  live,
  recent: [],
});

describe("advanceOverview", () => {
  it("moves running sessions and today's hours on", () => {
    const o = advanceOverview(overview([session({})]), 36);
    expect(o.live[0]).toMatchObject({ activeSeconds: 636, stateSeconds: 66, idleSeconds: 38 });
    expect(o.today.hours).toBeCloseTo(1.01);
    expect(o.today.bots.tanner).toBeCloseTo(1.01);
    expect(o.week.hours).toBeCloseTo(5.01);
    expect(o.totalHours).toBeCloseTo(50.01);
  });

  it("a paused session's active time stands still; its time in the state doesn't", () => {
    const o = advanceOverview(overview([session({ paused: true })]), 36);
    expect(o.live[0]).toMatchObject({ activeSeconds: 600, stateSeconds: 66 });
    expect(o.today.hours).toBe(1);
  });

  it("keeps an old log's unknown state unknown, and returns nothing new with nothing running", () => {
    expect(advanceOverview(overview([session({ state: null, stateSeconds: null })]), 5).live[0]!.stateSeconds).toBeNull();
    const idle = overview([]);
    expect(advanceOverview(idle, 5)).toBe(idle);
  });
});
