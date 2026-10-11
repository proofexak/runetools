/**
 * The Schedule card's pure parts (PRO-102): local days of a week in the schedule's timezone,
 * where bars sit in a day, and how closely what ran followed the plan. Times are epoch seconds.
 */
interface Span { start: number; end: number }

const formats = new Map<string, Intl.DateTimeFormat>();

function wall(tz: string, epoch: number): number[] {
  let f = formats.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz, hourCycle: "h23",
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    formats.set(tz, f);
  }
  const p = Object.fromEntries(f.formatToParts(new Date(epoch * 1000)).map((x) => [x.type, x.value]));
  return [p.year, p.month, p.day, p.hour, p.minute, p.second].map(Number);
}

function offset(tz: string, epoch: number): number {
  const [y, mo, d, h, mi, s] = wall(tz, epoch) as [number, number, number, number, number, number];
  return Date.UTC(y, mo - 1, d, h, mi, s) / 1000 - Math.floor(epoch);
}

/** The instant the zone's clock shows `date` + `secondsOfDay` (same as the API's). */
export function zonedEpoch(tz: string, date: string, secondsOfDay: number): number {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  const asUtc = Date.UTC(y, m - 1, d) / 1000 + secondsOfDay;
  return asUtc - offset(tz, asUtc - offset(tz, asUtc));
}

export function zonedDate(tz: string, epoch: number): string {
  const [y, m, d] = wall(tz, epoch) as [number, number, number];
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/** Seconds since the local midnight of that instant's day. */
export function zonedSeconds(tz: string, epoch: number): number {
  const [, , , h, mi, s] = wall(tz, epoch) as number[];
  return h! * 3600 + mi! * 60 + s!;
}

export function addDays(date: string, n: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function mondayOf(date: string): string {
  return addDays(date, -((new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7));
}

export interface Day { date: string; start: number; end: number }

/** The 7 local days from a Monday, each from its midnight to the next (23 / 25 h on DST days). */
export function weekDays(monday: string, tz: string): Day[] {
  return Array.from({ length: 7 }, (_, i) => {
    const date = addDays(monday, i);
    return { date, start: zonedEpoch(tz, date, 0), end: zonedEpoch(tz, addDays(date, 1), 0) };
  });
}

/** Where items sit in a day: left / width in percent of it, clipped to the day. */
export function segments<T extends Span>(items: T[], day: Span): { left: number; width: number; item: T }[] {
  const len = day.end - day.start;
  return items
    .filter((it) => it.end > day.start && it.start < day.end)
    .map((item) => {
      const a = Math.max(item.start, day.start), b = Math.min(item.end, day.end);
      return { left: (a - day.start) / len * 100, width: (b - a) / len * 100, item };
    });
}

const clip = (s: Span, from: number, to: number) => Math.max(0, Math.min(s.end, to) - Math.max(s.start, from));

export interface Adherence {
  plannedHours: number;     // all of the window's plan
  ranHours: number;         // what ran in the window, up to now
  ranInsideHours: number;   // … of it inside planned blocks
  outsideMinutes: number;   // … of it outside them
  missed: number;           // past blocks that ran less than 10 % of their time
  coverage: number | null;  // ranInside / planned so far; null = nothing planned so far
}

export function adherence(blocks: Span[], actual: Span[], from: number, to: number, now: number): Adherence {
  const upTo = Math.min(to, now);
  const planned = blocks.reduce((s, b) => s + clip(b, from, to), 0);
  const plannedSoFar = blocks.reduce((s, b) => s + clip(b, from, upTo), 0);
  const ran = actual.reduce((s, a) => s + clip(a, from, upTo), 0);
  const inside = (b: Span) => actual.reduce((s, a) => s + clip({ start: Math.max(a.start, b.start), end: Math.min(a.end, b.end) }, from, upTo), 0);
  const ranInside = blocks.reduce((s, b) => s + inside(b), 0);
  const missed = blocks.filter((b) => b.end <= now && b.end > from && b.start < to && inside(b) < 0.1 * (b.end - b.start)).length;
  return {
    plannedHours: planned / 3600,
    ranHours: ran / 3600,
    ranInsideHours: ranInside / 3600,
    outsideMinutes: (ran - ranInside) / 60,
    missed,
    coverage: plannedSoFar > 0 ? ranInside / plannedSoFar : null,
  };
}
