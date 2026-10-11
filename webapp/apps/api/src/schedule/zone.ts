/**
 * Local dates and times in an IANA zone (an account's schedule timezone), on Intl alone.
 * Epochs are in seconds; dates are "YYYY-MM-DD".
 */
const formats = new Map<string, Intl.DateTimeFormat>();

function format(tz: string): Intl.DateTimeFormat {
  let f = formats.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz, hourCycle: "h23",
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    formats.set(tz, f);
  }
  return f;
}

function wall(tz: string, epoch: number): number[] {
  const p = Object.fromEntries(format(tz).formatToParts(new Date(epoch * 1000)).map((x) => [x.type, x.value]));
  return [p.year, p.month, p.day, p.hour, p.minute, p.second].map(Number);
}

/** Seconds the zone's wall clock is ahead of UTC at that instant. */
function offset(tz: string, epoch: number): number {
  const [y, mo, d, h, mi, s] = wall(tz, epoch) as [number, number, number, number, number, number];
  return Date.UTC(y, mo - 1, d, h, mi, s) / 1000 - Math.floor(epoch);
}

/** The instant the zone's clock shows `date` + `secondsOfDay` (≥ 86400 rolls into the next days). */
export function zonedEpoch(tz: string, date: string, secondsOfDay: number): number {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  const asUtc = Date.UTC(y, m - 1, d) / 1000 + secondsOfDay;
  const first = asUtc - offset(tz, asUtc);
  return asUtc - offset(tz, first);           // second pass: the offset at the answer itself
}

/** The zone's local date at that instant. */
export function zonedDate(tz: string, epoch: number): string {
  const [y, m, d] = wall(tz, epoch) as [number, number, number];
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/** 0 = Monday … 6 = Sunday. */
export function weekday(date: string): number {
  return (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
}

export function addDays(date: string, n: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

/** Every date of a "YYYY-MM" month. */
export function monthDates(month: string): string[] {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const n = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return Array.from({ length: n }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`);
}
