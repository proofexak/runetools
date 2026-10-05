import type { LiveSession, Overview } from "@runetools/shared";
import { Activity, Pause } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router";
import { SessionsTable, StatTile, Swatch } from "@/components/common";
import { HoursChart } from "@/components/hours-chart";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { botColors } from "@/lib/bots";
import { accountLabel, botLabel, fmtClock, fmtHours, fmtNumber, fmtSeconds } from "@/lib/format";
import { useLiveOverview } from "@/lib/live";
import { useAllBots } from "@/lib/queries";
import { useIsDark } from "@/lib/theme";
import { cn } from "@/lib/utils";

/**
 * Live sessions, tiles, 14-day chart, today by bot and recent sessions for one overview —
 * the whole dashboard, or one account's page. `account` undefined = every account.
 * `live={false}` leaves the running sessions out, for a page that shows them elsewhere (LiveSessions).
 */
export function OverviewView({ o: fetched, account, stale = false, live = true }:
  { o: Overview; account: string | undefined; stale?: boolean; live?: boolean }) {
  const o = useLiveOverview(fetched);
  const filter = account === undefined ? "" : `account=${encodeURIComponent(account)}`;
  return (
    <div className={cn("grid grid-cols-1 gap-4 transition-opacity", stale && "opacity-60")}>
      {live && <LiveCard live={o.live} account={account} />}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Today" value={fmtHours(o.today.hours)}
          sub={`${fmtNumber(o.today.runs)} runs · ${o.today.sessions} session${o.today.sessions === 1 ? "" : "s"}`} />
        <StatTile label="Last 7 days" value={fmtHours(o.week.hours)} sub={`${fmtNumber(o.week.runs)} runs`} />
        <StatTile label="Crashes, 7 days" value={o.week.crashes}
          sub={o.week.crashes
            ? <Link to={`/sessions?status=crashed${filter && `&${filter}`}`} className="hover:underline">See sessions</Link>
            : "None"} />
        <StatTile label="All time" value={fmtHours(o.totalHours)} sub="active bot time" />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="grid gap-1.5">
              <CardTitle>Hours per day</CardTitle>
              <CardDescription>Last 14 days, by bot</CardDescription>
            </div>
          </CardHeader>
          <CardContent><HoursChart days={o.daily} /></CardContent>
        </Card>
        <TodayByBot overview={o} />
      </div>
      <Card className="gap-2">
        <CardHeader>
          <CardTitle>Recent sessions</CardTitle>
          <Link to={`/sessions${filter && `?${filter}`}`} className="text-muted-foreground text-sm hover:underline">All sessions</Link>
        </CardHeader>
        <CardContent className="px-3">
          <SessionsTable rows={o.recent.slice(0, 10)} now={o.now} showAccount={account === undefined} />
        </CardContent>
      </Card>
    </div>
  );
}

/** Just the running sessions of an overview (ticking), e.g. at the top of an account's page. */
export function LiveSessions({ o: fetched, account }: { o: Overview; account: string | undefined }) {
  const o = useLiveOverview(fetched);
  return <LiveCard live={o.live} account={account} />;
}

/** `account` undefined: every account's sessions, each labelled with its account. */
function LiveCard({ live, account }: { live: LiveSession[]; account: string | undefined }) {
  if (live.length === 0) {
    return (
      <Card className="text-muted-foreground flex-row items-center gap-3 px-5 py-4 text-sm">
        <Activity className="size-4" />
        {account === undefined ? "Nothing running right now." : `Nothing running on ${accountLabel(account)} right now.`}
      </Card>
    );
  }
  const showAccount = account === undefined;
  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="relative flex size-2.5">
            <span className="bg-success absolute inline-flex size-full animate-ping rounded-full opacity-60" />
            <span className="bg-success relative inline-flex size-2.5 rounded-full" />
          </span>
          Running now
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {live.map((s) => (
          <Link key={s.id} to={`/sessions/${s.id}`} className="hover:bg-accent/60 grid gap-1 rounded-lg border px-4 py-3 transition-colors">
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-medium">{botLabel(s.bot)}</span>
              {showAccount && <span className="text-muted-foreground truncate text-sm">{accountLabel(s.account)}</span>}
            </div>
            <div className="flex items-center gap-2 text-sm" data-testid="live-state">
              {s.state !== null ? (
                <>
                  <span className="font-mono text-[13px]">{s.state}</span>
                  {s.stateSeconds !== null && (
                    <span className="text-muted-foreground tabular-nums">for {fmtSeconds(s.stateSeconds)}</span>
                  )}
                </>
              ) : (
                // a log from before live status: only finished steps are known
                <>
                  <span className="text-muted-foreground">last step</span>
                  <span className="font-mono text-[13px]">{s.lastStep ?? "starting"}</span>
                </>
              )}
              {s.paused && <Badge variant="warning" className="ml-auto"><Pause />Paused</Badge>}
            </div>
            <div className="text-muted-foreground text-xs tabular-nums">
              {fmtClock(s.activeSeconds)} active · run {s.runs} · last event {fmtSeconds(s.idleSeconds)} ago
            </div>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

function TodayByBot({ overview }: { overview: Overview }) {
  const dark = useIsDark();
  const allBots = useAllBots();
  const entries = Object.entries(overview.today.bots).filter(([, h]) => h > 0).sort((a, b) => b[1] - a[1]);
  const colors = useMemo(() => botColors([...(allBots.data ?? []), ...entries.map(([b]) => b)], dark), [allBots.data, entries, dark]);
  const max = Math.max(...entries.map(([, h]) => h), 0);
  return (
    <Card>
      <CardHeader>
        <div className="grid gap-1.5">
          <CardTitle>Today by bot</CardTitle>
          <CardDescription>{fmtHours(overview.today.hours)} in total</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {entries.length === 0 && <p className="text-muted-foreground text-sm">No bot time yet today.</p>}
        {entries.map(([bot, hours]) => (
          <div key={bot} className="grid gap-1.5">
            <div className="flex items-center gap-2 text-sm">
              <Swatch color={colors.get(bot)!} />
              <span>{botLabel(bot)}</span>
              <span className="ml-auto tabular-nums">{fmtHours(hours)}</span>
            </div>
            <div className="h-1.5 rounded-full" style={{ width: `${(hours / max) * 100}%`, background: colors.get(bot) }} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function OverviewSkeleton() {
  return (
    <div className="grid gap-4">
      <Skeleton className="h-14" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}
      </div>
      <Skeleton className="h-80" />
    </div>
  );
}
