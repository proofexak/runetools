import type { SessionDetail, StepRow } from "@runetools/shared";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { ErrorNote, StatTile, StatusBadge } from "@/components/common";
import { PageHeader } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { accountLabel, botLabel, fmtClock, fmtDay, fmtHours, fmtNumber, fmtSeconds } from "@/lib/format";
import { useSession } from "@/lib/queries";
import { cn } from "@/lib/utils";

const FAILURES = new Set(["fail", "not_found"]);

export function SessionDetailPage() {
  const id = Number(useParams().id);
  const q = useSession(id);
  const s = q.data;

  return (
    <>
      <Button asChild variant="ghost" size="sm" className="text-muted-foreground mb-2 -ml-2">
        <Link to="/sessions"><ArrowLeft /> Sessions</Link>
      </Button>
      <ErrorNote error={q.error} />
      {!s ? (!q.error && <Skeleton className="h-64" />) : (
        <>
          <PageHeader
            title={`${botLabel(s.bot)} · ${fmtDay(s.startedAt.slice(0, 10))} ${s.startedAt.slice(11, 16)}`}
            description={`${accountLabel(s.account)} · session ${s.stamp ?? s.id}`}
          >
            <StatusBadge status={s.status} />
          </PageHeader>
          <div className="grid grid-cols-1 gap-4">
            {s.reason && <p className="text-sm"><span className="text-muted-foreground">Ended: </span>{s.reason}</p>}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatTile label="Active" value={fmtClock(s.activeSeconds)} sub={`${fmtClock(s.pausedSeconds)} paused in ${s.pauses} pause${s.pauses === 1 ? "" : "s"}`} />
              <StatTile label="Runs" value={fmtNumber(s.runs)}
                sub={s.activeSeconds >= 60 ? `${fmtNumber(s.runs / (s.activeSeconds / 3600), 1)} per hour` : "—"} />
              <StatTile label="Steps" value={fmtNumber(s.stateTime.reduce((a, x) => a + x.count, 0))}
                sub={`${s.stateTime.reduce((a, x) => a + x.failures, 0)} failed`} />
              <StatTile label="Errors" value={s.errors} sub={s.lastStep ? `last step ${s.lastStep}` : undefined} />
            </div>
            {s.errorList.length > 0 && <ErrorsCard session={s} />}
            <div className="grid gap-4 lg:grid-cols-2">
              <StateTimeCard session={s} />
              <ParamsCard session={s} />
            </div>
            <TimelineCard steps={s.steps} />
          </div>
        </>
      )}
    </>
  );
}

function ErrorsCard({ session }: { session: SessionDetail }) {
  return (
    <Card className="border-destructive/40">
      <CardHeader><CardTitle>Errors</CardTitle></CardHeader>
      <CardContent className="grid gap-4">
        {session.errorList.map((e, i) => (
          <div key={i} className="grid gap-2">
            <div className="text-sm">
              <span className="text-destructive font-medium">{e.type}</span>: {e.message}
              <span className="text-muted-foreground"> — in {e.state ?? "?"} ({e.where ?? "?"}), {e.ts.slice(11, 19)}</span>
            </div>
            {e.traceback && (
              <pre className="bg-muted overflow-x-auto rounded-md p-3 font-mono text-xs leading-relaxed">{e.traceback.trimEnd()}</pre>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function StateTimeCard({ session }: { session: SessionDetail }) {
  const max = Math.max(...session.stateTime.map((x) => x.seconds), 0);
  return (
    <Card className="gap-2">
      <CardHeader>
        <div className="grid gap-1.5">
          <CardTitle>Time per state</CardTitle>
          <CardDescription>Total step time, failures in red</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="px-3">
        {session.stateTime.length === 0 ? <p className="text-muted-foreground px-2 py-4 text-sm">No steps logged.</p> : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>State</TableHead>
                <TableHead className="w-1/3" />
                <TableHead className="text-right">Time</TableHead>
                <TableHead className="text-right">Steps</TableHead>
                <TableHead className="text-right">Failed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {session.stateTime.map((x) => (
                <TableRow key={x.state}>
                  <TableCell className="font-mono text-[13px]">{x.state}</TableCell>
                  <TableCell>
                    <div className="bg-primary/80 h-1.5 rounded-full" style={{ width: `${max ? (x.seconds / max) * 100 : 0}%` }} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmtSeconds(x.seconds)}</TableCell>
                  <TableCell className="text-right tabular-nums">{x.count}</TableCell>
                  <TableCell className={cn("text-right tabular-nums", x.failures ? "text-destructive font-medium" : "text-muted-foreground")}>
                    {x.failures ? `${x.failures} (${Math.round((x.failures / x.count) * 100)}%)` : "–"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function ParamsCard({ session }: { session: SessionDetail }) {
  const entries = Object.entries(session.params);
  return (
    <Card className="gap-3">
      <CardHeader><CardTitle>Session</CardTitle></CardHeader>
      <CardContent className="grid gap-1.5 text-sm">
        <Row label="Started" value={session.startedAt.replace("T", " ").slice(0, 19)} />
        <Row label="Ended" value={session.status === "running" ? "still running" : session.endedAt.replace("T", " ").slice(0, 19)} />
        <Row label="Wall time" value={fmtHours((Date.parse(session.endedAt) - Date.parse(session.startedAt)) / 3_600_000)} />
        <Row label="Log" value={<span className="font-mono text-xs break-all">{session.file}</span>} />
        {entries.length > 0 && <div className="text-muted-foreground mt-2 text-xs font-medium tracking-wide uppercase">Parameters</div>}
        {entries.map(([k, v]) => <Row key={k} label={k} value={<span className="font-mono text-[13px]">{JSON.stringify(v)}</span>} />)}
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="text-muted-foreground w-28 shrink-0">{label}</span>
      <span className="min-w-0">{value}</span>
    </div>
  );
}

function TimelineCard({ steps }: { steps: StepRow[] }) {
  const [onlyIssues, setOnlyIssues] = useState(false);
  const shown = onlyIssues ? steps.filter((s) => s.result !== "ok") : steps;
  return (
    <Card className="gap-2">
      <CardHeader>
        <div className="grid gap-1.5">
          <CardTitle>Step timeline</CardTitle>
          <CardDescription>{steps.length >= 2000 ? "Latest 2,000 steps" : `${steps.length} steps`}</CardDescription>
        </div>
        <Button variant={onlyIssues ? "secondary" : "ghost"} size="sm" onClick={() => setOnlyIssues(!onlyIssues)} aria-pressed={onlyIssues}>
          Only non-ok
        </Button>
      </CardHeader>
      <CardContent className="max-h-[32rem] overflow-y-auto px-3">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Time</TableHead>
              <TableHead className="text-right">Run</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Result</TableHead>
              <TableHead className="w-full text-right">Took</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((s, i) => (
              <TableRow key={i}>
                <TableCell className="text-muted-foreground tabular-nums">{s.ts.slice(11, 19)}</TableCell>
                <TableCell className="text-right tabular-nums">{s.run ?? "–"}</TableCell>
                <TableCell className="font-mono text-[13px]">{s.state}</TableCell>
                <TableCell>
                  <Badge variant={s.result === "ok" ? "muted" : FAILURES.has(s.result ?? "") ? "destructive" : "warning"}>{s.result ?? "–"}</Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">{fmtSeconds(s.seconds)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {shown.length === 0 && <p className="text-muted-foreground py-4 text-center text-sm">Nothing to show.</p>}
      </CardContent>
    </Card>
  );
}
