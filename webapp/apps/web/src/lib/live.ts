/**
 * Running sessions keep going between fetches: the overview's durations are as of the
 * response, and the page moves them on by the time since (PRO-99). A paused session's
 * active time stands still; its time in the current state doesn't.
 */
import type { Overview } from "@runetools/shared";
import { useEffect, useMemo, useState } from "react";

export function advanceOverview(o: Overview, elapsed: number): Overview {
  if (elapsed <= 0 || o.live.length === 0) return o;
  let extra = 0;
  const bots = { ...o.today.bots };
  const live = o.live.map((s) => {
    const running = s.paused ? 0 : elapsed;
    extra += running;
    const bot = s.bot ?? "?";
    bots[bot] = (bots[bot] ?? 0) + running / 3600;
    return {
      ...s,
      activeSeconds: s.activeSeconds + running,
      stateSeconds: s.stateSeconds === null ? null : s.stateSeconds + elapsed,
      idleSeconds: s.idleSeconds + elapsed,
    };
  });
  const hours = extra / 3600;
  return {
    ...o,
    live,
    today: { ...o.today, hours: o.today.hours + hours, bots },
    week: { ...o.week, hours: o.week.hours + hours },
    totalHours: o.totalHours + hours,
  };
}

/** Date.now(), refreshed every `ms` while `active`. */
export function useNow(active: boolean, ms = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [active, ms]);
  return now;
}

/** The overview with its running sessions moved on to this second. */
export function useLiveOverview(o: Overview): Overview {
  const receivedAt = useMemo(() => Date.now(), [o]);
  const now = useNow(o.live.length > 0);
  return useMemo(() => advanceOverview(o, Math.max(0, (now - receivedAt) / 1000)), [o, now, receivedAt]);
}
