import { describe, expect, it } from "vitest";
import { botLabel, fmtClock, fmtDay, fmtHours, fmtSeconds, fmtWhen, statusTone } from "./format";
import { botColors } from "./bots";

describe("format", () => {
  it("hours", () => {
    expect(fmtHours(0)).toBe("0m");
    expect(fmtHours(0.5)).toBe("30m");
    expect(fmtHours(2)).toBe("2h");
    expect(fmtHours(2.26)).toBe("2h 16m");
  });

  it("seconds and clock", () => {
    expect(fmtSeconds(42.4)).toBe("42s");
    expect(fmtSeconds(125)).toBe("2m 05s");
    expect(fmtSeconds(7260)).toBe("2h 1m");
    expect(fmtClock(3723.9)).toBe("1:02:03");
  });

  it("days and times", () => {
    expect(fmtDay("2026-10-05")).toBe("Oct 5");
    expect(fmtDay("2026-10-05", true)).toBe("Mon Oct 5");
    expect(fmtWhen("2026-10-05T15:17:12.569", "2026-10-05T18:00:00")).toBe("15:17");
    expect(fmtWhen("2026-10-04T15:17:12.569", "2026-10-05T18:00:00")).toBe("Oct 4, 15:17");
  });

  it("labels", () => {
    expect(botLabel("golden_nuggets")).toBe("Golden nuggets");
    expect(botLabel(null)).toBe("Unknown");
    expect(statusTone("crashed")).toBe("destructive");
  });
});

describe("botColors", () => {
  it("colour follows the bot, not what is in view", () => {
    const all = botColors(["varrock_exp", "tanner", "golden_nuggets"], false);
    const again = botColors(["tanner", "golden_nuggets", "varrock_exp", "tanner"], false);
    expect(again).toEqual(all);
    expect(all.get("golden_nuggets")).toBe("#2a78d6");
    expect(botColors(["a", "b"], true).get("a")).toBe("#3987e5");
  });
});
