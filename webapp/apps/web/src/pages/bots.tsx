import type { BotStats } from "@runetools/shared";
import { X } from "lucide-react";
import { useSearchParams } from "react-router";
import { AccountFilter, ErrorNote, StatusBadge, useAccountParam } from "@/components/common";
import { PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { botLabel, fmtHours, fmtNumber } from "@/lib/format";
import { useBotStats } from "@/lib/queries";
import { cn } from "@/lib/utils";

export function BotStatsPage() {
  const [account] = useAccountParam();
  const [params, setParams] = useSearchParams();
  const since = params.get("since") || undefined;
  const q = useBotStats(account, since);

  return (
    <>
      <PageHeader title="Bot stats" description="Long-term numbers per bot, from every logged session" />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <AccountFilter />
        <span className="text-muted-foreground text-sm">since</span>
        <Input aria-label="Since" type="date" className="w-40" value={since ?? ""}
          onChange={(e) => setParams((p) => { if (e.target.value) p.set("since", e.target.value); else p.delete("since"); return p; }, { replace: true })} />
        {since && <Button variant="ghost" size="icon-sm" aria-label="Clear date" onClick={() => setParams((p) => { p.delete("since"); return p; })}><X /></Button>}
      </div>
      <ErrorNote error={q.error} />
      {!q.data ? <Skeleton className="h-64" /> : (
        <div className={cn("grid grid-cols-1 gap-4 transition-opacity", q.isPlaceholderData && "opacity-60")}>
          {q.data.bots.length === 0 && <p className="text-muted-foreground text-sm">No sessions in this range.</p>}
          {q.data.bots.map((b) => <BotCard key={b.bot} stats={b} />)}
        </div>
      )}
    </>
  );
}

function BotCard({ stats: b }: { stats: BotStats }) {
  return (
    <Card>
      <CardHeader>
        <div className="grid gap-1.5">
          <CardTitle className="text-lg">{botLabel(b.bot)}</CardTitle>
          <CardDescription>
            {b.sessions} session{b.sessions === 1 ? "" : "s"} · {fmtHours(b.activeHours)} active · {fmtNumber(b.runs)} runs
          </CardDescription>
        </div>
        <div className="flex flex-wrap justify-end gap-1">
          {Object.entries(b.finals).sort((x, y) => y[1] - x[1]).map(([status, n]) => (
            <span key={status} className="flex items-center gap-1 text-sm"><StatusBadge status={status} /><span className="tabular-nums">{n}</span></span>
          ))}
        </div>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-3">
        <div className="grid content-start gap-3">
          <Metric label="Runs per hour" value={fmtNumber(b.runsPerHour, 1)} />
          <Metric label="Recoveries per hour" value={fmtNumber(b.recoveriesPerHour, 2)} />
          {b.reasons.length > 0 && (
            <div className="grid gap-1">
              <div className="text-muted-foreground text-xs">Top stop reasons</div>
              {b.reasons.map((r) => (
                <div key={r.reason} className="flex justify-between gap-3 text-sm">
                  <span className="truncate" title={r.reason}>{r.reason}</span>
                  <span className="text-muted-foreground tabular-nums">{r.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="lg:col-span-2 grid content-start gap-6 md:grid-cols-2">
          <div>
            <div className="text-muted-foreground mb-1 text-xs">Failures by state</div>
            {b.failuresByState.length === 0 ? <p className="text-sm">No failed steps.</p> : (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="pl-0">State</TableHead>
                    <TableHead className="text-right">Failed</TableHead>
                    <TableHead className="text-right">of steps</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {b.failuresByState.map((f) => (
                    <TableRow key={f.state}>
                      <TableCell className="pl-0 font-mono text-[13px]">{f.state}</TableCell>
                      <TableCell className="text-right tabular-nums">{f.failures}</TableCell>
                      <TableCell className="text-right tabular-nums">{Math.round(f.rate * 100)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
          <div>
            <div className="text-muted-foreground mb-1 text-xs">Crash types</div>
            {b.crashTypes.length === 0 ? <p className="text-sm">No crashes.</p> : b.crashTypes.map((c) => (
              <div key={c.type} className="flex justify-between gap-3 border-b py-2 text-sm last:border-0">
                <span className="text-destructive font-mono text-[13px]">{c.type}</span>
                <span className="tabular-nums">{c.count}</span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="text-xl font-semibold">{value}</div>
    </div>
  );
}
