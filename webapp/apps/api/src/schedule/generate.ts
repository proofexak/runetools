/**
 * Play-schedule generator (PRO-102) — pure and seeded: the same account, seed and month always
 * give the same blocks, and two accounts never share a shape. Numbers from the research
 * (https://claude.ai/code/artifact/5b50a90e-0d50-476d-9911-e547fd91a75b): a heavy human player —
 * the month's target (default 200 h) over play days with a day or two off each week, 1–3
 * heavy-tailed (Weibull) sessions a day, evening starts in the account's own timezone, longer
 * weekends; never a session near the game's 6 h logout, never a round duration.
 */
import { createHash } from "node:crypto";
import { addDays, daysBetween, monthDates, weekday, zonedDate, zonedEpoch } from "./zone.js";

export interface Activity { bot: string; launch: string; value: string | null; weight: number }

export interface ScheduleProfileInput {
  /** The account's stable key (the API passes its id, so a rename keeps the plan). */
  account: string;
  seed: number;
  timezone: string;
  monthlyHours: number;
  activities: Activity[];
  rampStart: string | null;
}

/** start / end in epoch seconds. */
export interface PlannedBlock { start: number; end: number; bot: string; launch: string; value: string | null }

export interface Traits {
  weekdayAnchor: number;   // first start on a weekday, seconds of the local day
  weekendAnchor: number;
  startSd: number;         // day-to-day spread of that start, s
  sessionsMean: number;    // sessions on a play day
  weibullShape: number;    // session lengths: < 1 = heavy-tailed
  weekendMult: number;     // weekend days weigh this much more
  offTwoProb: number;      // chance a week has two days off instead of one
  bedtime: number;         // usual last logout, seconds after the day's midnight (23:30–01:30)
}

export const SESSION_MAX = 16_200;     // 4.5 h: well under the game's 6 h logout
const SESSION_AIM = 3 * 3600;          // enough sessions that few press against the cap
export const SESSION_MIN = 600;
export const DAY_MAX = 11 * 3600;
export const GAP_MIN = 1200, GAP_MAX = 10_800;
const EARLIEST = 8 * 3600;             // first start not before 08:00 local
const LAST_START = 23.5 * 3600;        // the day's last session starts by 23:30 …
const LATEST = 27 * 3600;              // … and ends by 03:00 whatever the bedtime
const RAMP_DAYS = 14;

type Rng = () => number;

/** mulberry32 seeded from sha256(key). */
function rng(key: string): Rng {
  let a = createHash("sha256").update(key).digest().readUInt32LE(0);
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const uniform = (r: Rng, a: number, b: number) => a + (b - a) * r();
const normal = (r: Rng) => Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r());
const lognormal = (r: Rng, mu: number, sigma: number) => Math.exp(mu + sigma * normal(r));
const weibull = (r: Rng, k: number) => (-Math.log(1 - r())) ** (1 / k);

function poisson(r: Rng, lambda: number): number {
  const limit = Math.exp(-lambda);
  let k = 0, p = r();
  while (p > limit) { k++; p *= r(); }
  return k;
}

export function traits(account: string, seed: number): Traits {
  const r = rng(`${account}:${seed}`);
  const weekdayAnchor = uniform(r, 17, 20.5) * 3600;
  return {
    weekdayAnchor,
    weekendAnchor: weekdayAnchor - uniform(r, 2, 4) * 3600,
    startSd: uniform(r, 60, 90) * 60,
    sessionsMean: uniform(r, 1.1, 2.1),
    weibullShape: uniform(r, 0.6, 0.8),
    weekendMult: uniform(r, 1.1, 1.5),
    offTwoProb: uniform(r, 0.2, 0.35),
    bedtime: uniform(r, 23.5, 25.5) * 3600,
  };
}

function rampFactor(p: ScheduleProfileInput, date: string): number {
  if (!p.rampStart) return 1;
  const d = daysBetween(p.rampStart, date);
  return d < 0 ? 0 : Math.min(1, 0.3 + 0.7 * d / RAMP_DAYS);
}

/** Split `total` seconds into session lengths: Weibull-shaped, each within SESSION_MIN..MAX. */
function sessionLengths(r: Rng, t: Traits, total: number): number[] {
  const most = Math.max(1, Math.floor(total / SESSION_MIN));
  const k = Math.min(most, Math.max(Math.ceil(total / SESSION_AIM), 1 + poisson(r, t.sessionsMean - 1)));
  const draws = Array.from({ length: k }, () => weibull(r, t.weibullShape) + 0.05);
  const sum = draws.reduce((s, x) => s + x, 0);
  const pieces = draws.map((x) => total * x / sum);
  for (let pass = 0; pass < 50; pass++) {
    const big = pieces.findIndex((x) => x > SESSION_MAX);
    if (big < 0) break;
    const small = pieces.indexOf(Math.min(...pieces));
    const capped = SESSION_MAX - uniform(r, 0, 1800);   // not all at one length
    const excess = pieces[big]! - capped;
    pieces[big] = capped;
    pieces[small]! += excess;
  }
  for (let i = pieces.length - 1; i >= 0 && pieces.length > 1; i--) {
    if (pieces[i]! >= SESSION_MIN) continue;
    const [tiny] = pieces.splice(i, 1);
    const j = pieces.indexOf(Math.min(...pieces));
    pieces[j] = Math.min(SESSION_MAX, pieces[j]! + tiny!);
  }
  return pieces.map((x) => {
    let s = Math.floor(x);                  // floor: the pieces never add up past the day
    if (s % 60 === 0) {                     // never a whole number of minutes; down keeps the caps
      const nudge = 1 + Math.floor(r() * 59);
      s = s - nudge < SESSION_MIN ? s + nudge : s - nudge;
    }
    return s;
  });
}

function pickActivity(r: Rng, acts: Activity[], since: number[]): number {
  const scores = acts.map((a, i) => a.weight * (1 + since[i]!));
  let x = r() * scores.reduce((s, v) => s + v, 0);
  let chosen = scores.length - 1;
  for (let i = 0; i < scores.length; i++) {
    x -= scores[i]!;
    if (x < 0 && scores[i]! > 0) { chosen = i; break; }
  }
  since.forEach((_, i) => { since[i] = i === chosen ? 0 : since[i]! + 1; });
  return chosen;
}

/** The blocks of one "YYYY-MM" month in the profile's timezone, sorted, never overlapping. */
export function generateMonth(p: ScheduleProfileInput, month: string): PlannedBlock[] {
  const acts = p.activities.filter((a) => a.weight > 0);
  if (acts.length === 0 || p.monthlyHours <= 0) return [];
  const t = traits(p.account, p.seed);
  const dates = monthDates(month);

  // days off and the week's intensity, drawn per Monday so a week split across months agrees —
  // and without the seed: a habit of the account's, so a Regenerate mid-week keeps the week's days off
  const off = new Set<string>();
  const weekFactor = new Map<string, number>();
  for (let monday = addDays(dates[0]!, -weekday(dates[0]!)); monday <= dates.at(-1)!; monday = addDays(monday, 7)) {
    const wr = rng(`${p.account}:week:${monday}`);
    const n = wr() < t.offTwoProb ? 2 : 1;
    const days = [0, 1, 2, 3, 4, 5, 6];
    for (let i = 0; i < n; i++) off.add(addDays(monday, days.splice(Math.floor(wr() * days.length), 1)[0]!));
    weekFactor.set(monday, lognormal(wr, 0, 0.15));
  }

  const r = rng(`${p.account}:${p.seed}:${month}`);
  const target = p.monthlyHours * 3600 * dates.reduce((s, d) => s + rampFactor(p, d), 0) / 30;
  const weights = dates.map((d) => {
    const noise = lognormal(r, 0, 0.25);
    if (off.has(d)) return 0;
    const weekend = weekday(d) >= 5 ? t.weekendMult : 1;
    return noise * weekend * weekFactor.get(addDays(d, -weekday(d)))! * rampFactor(p, d);
  });
  const sumW = weights.reduce((s, w) => s + w, 0);
  if (sumW <= 0) return [];

  // seconds per day, capped at DAY_MAX with the excess spread over the days under the cap
  const secs = weights.map((w) => target * w / sumW);
  for (let pass = 0; pass < 20; pass++) {
    const excess = secs.reduce((s, x) => s + Math.max(0, x - DAY_MAX), 0);
    if (excess < 1) break;
    const room = weights.map((w, i) => (w > 0 && secs[i]! < DAY_MAX ? w : 0));
    const roomW = room.reduce((s, w) => s + w, 0);
    for (let i = 0; i < secs.length; i++) {
      secs[i] = Math.min(secs[i]!, DAY_MAX) + (roomW > 0 ? excess * room[i]! / roomW : 0);
    }
  }

  const since = acts.map(() => 0);
  const blocks: PlannedBlock[] = [];
  dates.forEach((date, i) => {
    const total = Math.min(secs[i]!, DAY_MAX);
    if (total < SESSION_MIN) return;
    const lengths = sessionLengths(r, t, total);
    let gaps = lengths.slice(1).map(() => Math.round(Math.min(GAP_MAX, Math.max(GAP_MIN, lognormal(r, Math.log(3000), 0.6)))));
    const busy = lengths.reduce((s, x) => s + x, 0);
    // the day's last logout: by the account's bedtime (later on Friday / Saturday, ±45 min),
    // often a while before it — logouts cluster at night, never on one minute
    const late = weekday(date) === 4 || weekday(date) === 5 ? uniform(r, 0.5, 1.5) * 3600 : 0;
    const slack = Math.abs(normal(r)) * 2400;
    const bedtime = Math.min(LATEST, t.bedtime + late + normal(r) * 2700 - slack);
    const window = bedtime - EARLIEST;
    if (busy + gaps.reduce((s, g) => s + g, 0) > window) {     // squeeze the gaps to fit the day
      gaps = gaps.map(() => Math.max(GAP_MIN, Math.floor((window - busy) / Math.max(1, gaps.length))));
    }
    const span = busy + gaps.reduce((s, g) => s + g, 0);
    const anchor = weekday(date) >= 5 ? t.weekendAnchor : t.weekdayAnchor;
    let start = anchor + normal(r) * t.startSd;
    start = Math.min(start, bedtime - span, LAST_START - (span - lengths.at(-1)!));
    start = Math.round(Math.max(start, EARLIEST));
    let at = zonedEpoch(p.timezone, date, start);
    lengths.forEach((len, j) => {
      const a = acts[pickActivity(r, acts, since)]!;
      blocks.push({ start: at, end: at + len, bot: a.bot, launch: a.launch, value: a.value });
      at += len + (gaps[j] ?? 0);
    });
  });
  return blocks;
}

/** The blocks starting in [fromEpoch, toEpoch): every month that range touches, generated whole. */
export function generateRange(p: ScheduleProfileInput, fromEpoch: number, toEpoch: number): PlannedBlock[] {
  const first = zonedDate(p.timezone, fromEpoch).slice(0, 7);
  const last = zonedDate(p.timezone, toEpoch).slice(0, 7);
  const out: PlannedBlock[] = [];
  for (let month = first; month <= last; month = addDays(`${month}-28`, 7).slice(0, 7)) {
    out.push(...generateMonth(p, month).filter((b) => b.start >= fromEpoch && b.start < toEpoch));
  }
  return out;
}
