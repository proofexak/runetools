import { describe, expect, it } from "vitest";
import { adherence, mondayOf, segments, weekDays, zonedEpoch } from "./schedule";

const TZ = "Europe/Warsaw";
const H = 3600;

describe("weekDays", () => {
  it("seven local days, the DST Sunday 25 h long", () => {
    const days = weekDays("2026-10-19", TZ);
    expect(days.map((d) => d.date)).toEqual(["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22",
      "2026-10-23", "2026-10-24", "2026-10-25"]);
    expect(days.slice(0, 6).every((d) => d.end - d.start === 24 * H)).toBe(true);
    expect(days[6]!.end - days[6]!.start).toBe(25 * H);
    expect(days[0]!.start).toBe(zonedEpoch(TZ, "2026-10-19", 0));
    expect(days[0]!.end).toBe(days[1]!.start);
  });

  it("mondayOf finds the week's Monday", () => {
    expect(mondayOf("2026-10-25")).toBe("2026-10-19");
    expect(mondayOf("2026-10-19")).toBe("2026-10-19");
    expect(mondayOf("2026-10-13")).toBe("2026-10-12");
  });
});

describe("segments", () => {
  it("places items as percents of the day and splits one crossing midnight", () => {
    const [d1, d2] = weekDays("2026-11-02", TZ);
    const item = { start: d1!.start + 22 * H, end: d1!.start + 26 * H };
    const a = segments([item], d1!);
    expect(a).toHaveLength(1);
    expect(a[0]!.left).toBeCloseTo(22 / 24 * 100);
    expect(a[0]!.width).toBeCloseTo(2 / 24 * 100);
    const b = segments([item], d2!);
    expect(b[0]!.left).toBe(0);
    expect(b[0]!.width).toBeCloseTo(2 / 24 * 100);
    expect(b[0]!.item).toBe(item);
    expect(segments([{ start: d1!.start - 2 * H, end: d1!.start - H }], d1!)).toEqual([]);
  });
});

describe("adherence", () => {
  it("counts what ran inside and outside the plan, so far", () => {
    const t0 = 1_800_000_000;
    const blocks = [
      { start: t0, end: t0 + 2 * H },               // ran 1.5 h of it
      { start: t0 + 4 * H, end: t0 + 5 * H },       // never ran: missed
      { start: t0 + 20 * H, end: t0 + 22 * H },     // still ahead
    ];
    const actual = [
      { start: t0 + 0.5 * H, end: t0 + 2.5 * H },   // 1.5 h inside, 0.5 h after the block
    ];
    const a = adherence(blocks, actual, t0 - H, t0 + 24 * H, t0 + 10 * H);
    expect(a.plannedHours).toBeCloseTo(5);
    expect(a.ranHours).toBeCloseTo(2);
    expect(a.ranInsideHours).toBeCloseTo(1.5);
    expect(a.outsideMinutes).toBeCloseTo(30);
    expect(a.missed).toBe(1);
    expect(a.coverage).toBeCloseTo(1.5 / 3);          // planned so far: 2 h + 1 h
  });

  it("nothing planned yet: no coverage, no division by zero", () => {
    const a = adherence([], [], 0, 100, 50);
    expect(a).toMatchObject({ plannedHours: 0, ranHours: 0, coverage: null, missed: 0 });
  });
});
