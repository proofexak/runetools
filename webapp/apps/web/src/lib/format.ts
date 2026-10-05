/** Display helpers. Timestamps are the bots' naive local wall time ("2026-10-05T15:17:12.569"). */

export function fmtHours(hours: number): string {
  const minutes = Math.round(hours * 60);
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function fmtSeconds(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return fmtHours(s / 3600);
}

/** "h:mm:ss", as logreport prints durations. */
export function fmtClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export const fmtNumber = (n: number, digits = 0) =>
  n.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Oct 5, 15:17" — or "15:17" when it is today (by the date part of `now`). */
export function fmtWhen(ts: string, now?: string): string {
  const time = ts.slice(11, 16);
  if (now && ts.slice(0, 10) === now.slice(0, 10)) return time;
  return `${fmtDay(ts.slice(0, 10))}, ${time}`;
}

export function fmtDay(day: string, withWeekday = false): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const label = `${MONTHS[m - 1]} ${d}`;
  if (!withWeekday) return label;
  const wd = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
  return `${wd} ${label}`;
}

/** "tanner" → "Tanner", "golden_nuggets" → "Golden nuggets". */
export function botLabel(bot: string | null): string {
  if (!bot) return "Unknown";
  const s = bot.replaceAll("_", " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function accountLabel(account: string | null): string {
  return account ? account : "Unassigned";
}

export type StatusTone = "success" | "destructive" | "warning" | "muted" | "default";

export function statusTone(status: string): StatusTone {
  switch (status) {
    case "running": return "default";
    case "done": return "success";
    case "crashed": return "destructive";
    case "killed": case "interrupted": return "warning";
    default: return "muted";
  }
}
