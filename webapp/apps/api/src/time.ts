/** Naive local wall-clock time, the same shape the bots log: "2026-10-05T15:17:12.569". */
export function localIso(d: Date = new Date()): string {
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:` +
    `${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

/** Postgres renders timestamps with a space; the API always answers with the "T" form. */
export function iso(ts: string): string;
export function iso(ts: string | null): string | null;
export function iso(ts: string | null): string | null {
  return ts === null ? null : ts.replace(" ", "T");
}

/** Seconds between two naive wall-clock strings (both read as the same zone). */
export function secondsBetween(a: string, b: string): number {
  return (Date.parse(iso(b)) - Date.parse(iso(a))) / 1000;
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
