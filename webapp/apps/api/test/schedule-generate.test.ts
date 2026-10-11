import { describe, expect, it } from "vitest";
import { generateMonth, generateRange, traits, type PlannedBlock, type ScheduleProfileInput } from "../src/schedule/generate.js";
import { weekday, zonedDate, zonedEpoch } from "../src/schedule/zone.js";

const TZ = "Europe/Warsaw";
const base: ScheduleProfileInput = {
  account: "alt1", seed: 0, timezone: TZ, monthlyHours: 200, rampStart: null,
  activities: [
    { bot: "Tanning", launch: "Green Dragonhide", value: "Al Kharid", weight: 1 },
    { bot: "Tanning", launch: "Blue Dragonhide", value: "Al Kharid", weight: 1 },
  ],
};

const hours = (bs: PlannedBlock[]) => bs.reduce((s, b) => s + b.end - b.start, 0) / 3600;
const byDay = (bs: PlannedBlock[]) => {
  const days = new Map<string, PlannedBlock[]>();
  for (const b of bs) {
    const d = zonedDate(TZ, b.start);
    days.set(d, [...(days.get(d) ?? []), b]);
  }
  return days;
};
const dates = (month: string) => {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const n = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return Array.from({ length: n }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`);
};

describe("zone", () => {
  it("zonedEpoch / zonedDate round-trip", () => {
    const t = zonedEpoch(TZ, "2026-07-01", 0);
    expect(t).toBe(Date.UTC(2026, 5, 30, 22) / 1000);          // CEST = UTC+2
    expect(zonedDate(TZ, t)).toBe("2026-07-01");
    expect(zonedEpoch(TZ, "2026-01-15", 3600)).toBe(Date.UTC(2026, 0, 15, 0) / 1000);   // CET
    expect(zonedEpoch(TZ, "2026-07-01", 86400 + 60)).toBe(zonedEpoch(TZ, "2026-07-02", 60));
  });

  it("weekday is 0 for Monday", () => {
    expect(weekday("2026-10-12")).toBe(0);
    expect(weekday("2026-10-18")).toBe(6);
  });
});

describe("generateMonth", () => {
  it("month total within 5% of the target", () => {
    expect(hours(generateMonth(base, "2026-11"))).toBeGreaterThanOrEqual(190);
    expect(hours(generateMonth(base, "2026-11"))).toBeLessThanOrEqual(210);
    const dec = hours(generateMonth(base, "2026-12"));
    expect(Math.abs(dec - 200 * 31 / 30) / (200 * 31 / 30)).toBeLessThanOrEqual(0.05);
  });

  it("sessions respect the caps", () => {
    for (const month of ["2026-11", "2026-12", "2027-01"]) {
      const bs = generateMonth(base, month);
      for (const b of bs) {
        expect(b.end - b.start).toBeLessThanOrEqual(16200);
        expect(b.end - b.start).toBeGreaterThanOrEqual(600);
        expect((b.end - b.start) % 60).not.toBe(0);
      }
      for (const day of byDay(bs).values()) {
        expect(hours(day)).toBeLessThanOrEqual(11 + 1e-9);
        for (let i = 1; i < day.length; i++) {
          const gap = day[i]!.start - day[i - 1]!.end;
          expect(gap).toBeGreaterThanOrEqual(1200);
          expect(gap).toBeLessThanOrEqual(10800);
        }
      }
    }
  });

  it("at least one day off each week", () => {
    const month = "2026-11";
    const played = new Set(byDay(generateMonth(base, month)).keys());
    const all = dates(month);
    for (let i = 0; i < all.length; i++) {
      if (weekday(all[i]!) !== 0 || i + 7 > all.length) continue;
      const week = all.slice(i, i + 7);
      expect(week.some((d) => !played.has(d))).toBe(true);
    }
  });

  it("generates across DST without overlaps", () => {
    for (const month of ["2026-10", "2027-03"]) {
      const bs = generateMonth(base, month);
      expect(bs.length).toBeGreaterThan(20);
      for (let i = 1; i < bs.length; i++) expect(bs[i - 1]!.end).toBeLessThanOrEqual(bs[i]!.start);
    }
  });

  it("deterministic and per account", () => {
    const a = generateMonth(base, "2026-11");
    expect(generateMonth(base, "2026-11")).toEqual(a);
    const starts = (bs: PlannedBlock[]) => bs.map((b) => b.start).join();
    expect(starts(generateMonth({ ...base, account: "alt2" }, "2026-11"))).not.toBe(starts(a));
    expect(starts(generateMonth({ ...base, seed: 1 }, "2026-11"))).not.toBe(starts(a));
  });

  it("weekdays start in the afternoon, weekends earlier", () => {
    // 200 h/month is ~7.7 h a play day: the day can't start in the evening, it ends there
    const firsts = { weekday: [] as number[], weekend: [] as number[] };
    for (const [d, day] of byDay(generateMonth(base, "2026-11"))) {
      firsts[weekday(d) >= 5 ? "weekend" : "weekday"].push((day[0]!.start - zonedEpoch(TZ, d, 0)) / 3600);
    }
    const median = (xs: number[]) => [...xs].sort((x, y) => x - y)[Math.floor(xs.length / 2)]!;
    expect(median(firsts.weekday)).toBeGreaterThanOrEqual(11);
    expect(median(firsts.weekday)).toBeLessThanOrEqual(20);
    expect(median(firsts.weekend)).toBeLessThan(median(firsts.weekday));
  });

  it("lighter months start in the evening", () => {
    const firsts: number[] = [];
    for (const [d, day] of byDay(generateMonth({ ...base, monthlyHours: 60 }, "2026-11"))) {
      if (weekday(d) < 5) firsts.push((day[0]!.start - zonedEpoch(TZ, d, 0)) / 3600);
    }
    const median = [...firsts].sort((x, y) => x - y)[Math.floor(firsts.length / 2)]!;
    expect(median).toBeGreaterThanOrEqual(16);
    expect(median).toBeLessThanOrEqual(22);
  });

  it("uses every activity, never a weight-0 one", () => {
    const launches = new Set(generateMonth(base, "2026-11").map((b) => b.launch));
    expect(launches).toEqual(new Set(["Green Dragonhide", "Blue Dragonhide"]));
    const zero = { ...base, activities: [base.activities[0]!, { ...base.activities[1]!, weight: 0 }] };
    expect(new Set(generateMonth(zero, "2026-11").map((b) => b.launch))).toEqual(new Set(["Green Dragonhide"]));
    expect(generateMonth(zero, "2026-11").every((b) => b.bot === "Tanning" && b.value === "Al Kharid")).toBe(true);
  });

  it("ramp lowers the first days", () => {
    const p = { ...base, rampStart: "2026-11-01" };
    const days = byDay(generateMonth(p, "2026-11"));
    const sum = (ds: string[]) => ds.reduce((s, d) => s + hours(days.get(d) ?? []), 0);
    expect(sum(["2026-11-01", "2026-11-02", "2026-11-03"]))
      .toBeLessThan(sum(["2026-11-20", "2026-11-21", "2026-11-22"]));
    const ramped = dates("2026-11").reduce((s, _d, i) => s + Math.min(1, 0.3 + 0.7 * i / 14), 0) / 30 * 200;
    expect(Math.abs(hours(generateMonth(p, "2026-11")) - ramped) / ramped).toBeLessThanOrEqual(0.05);
  });

  it("days don't all end at one hour", () => {
    for (const account of ["alt1", "alt2", "main"]) {
      const days = byDay(generateMonth({ ...base, account }, "2026-11"));
      const buckets = new Map<number, number>();
      for (const day of days.values()) {
        const end = Math.floor(day.at(-1)!.end / 600);          // 10-minute bucket of the day's last logout
        const key = end % 144;
        buckets.set(key, (buckets.get(key) ?? 0) + 1);
      }
      expect(Math.max(...buckets.values())).toBeLessThanOrEqual(4);   // ≤ 1 day in 6 on one 10-min slot
    }
  });

  it("sessions at the length cap are rare", () => {
    for (const account of ["alt1", "alt2", "main"]) {
      const bs = generateMonth({ ...base, account }, "2026-11");
      const atCap = bs.filter((b) => b.end - b.start >= 4.4 * 3600).length;
      expect(atCap / bs.length).toBeLessThanOrEqual(0.15);
    }
  });

  it("no activities → no blocks", () => {
    expect(generateMonth({ ...base, activities: [] }, "2026-11")).toEqual([]);
  });

  it("traits stay in their ranges", () => {
    for (const account of ["alt1", "alt2", "main", "x"]) {
      const t = traits(account, 0);
      expect(t.weekdayAnchor).toBeGreaterThanOrEqual(17 * 3600);
      expect(t.weekdayAnchor).toBeLessThanOrEqual(20.5 * 3600);
      expect(t.weekdayAnchor - t.weekendAnchor).toBeGreaterThanOrEqual(2 * 3600);
      expect(t.weekdayAnchor - t.weekendAnchor).toBeLessThanOrEqual(4 * 3600);
      expect(t.startSd).toBeGreaterThanOrEqual(3600);
      expect(t.startSd).toBeLessThanOrEqual(5400);
      expect(t.sessionsMean).toBeGreaterThanOrEqual(1.1);
      expect(t.sessionsMean).toBeLessThanOrEqual(2.1);
      expect(t.weibullShape).toBeGreaterThanOrEqual(0.6);
      expect(t.weibullShape).toBeLessThanOrEqual(0.8);
      expect(t.weekendMult).toBeGreaterThanOrEqual(1.1);
      expect(t.weekendMult).toBeLessThanOrEqual(1.5);
      expect(t.bedtime).toBeGreaterThanOrEqual(23.5 * 3600);
      expect(t.bedtime).toBeLessThanOrEqual(25.5 * 3600);
    }
  });
});

describe("generateRange", () => {
  it("covers the range across a month boundary, blocks starting inside it", () => {
    const from = zonedEpoch(TZ, "2026-11-25", 0), to = zonedEpoch(TZ, "2026-12-09", 0);
    const bs = generateRange(base, from, to);
    expect(bs.length).toBeGreaterThan(10);
    expect(bs.every((b) => b.start >= from && b.start < to)).toBe(true);
    expect(bs.some((b) => zonedDate(TZ, b.start).startsWith("2026-12"))).toBe(true);
    expect(bs).toEqual([...generateMonth(base, "2026-11"), ...generateMonth(base, "2026-12")]
      .filter((b) => b.start >= from && b.start < to));
  });
});
