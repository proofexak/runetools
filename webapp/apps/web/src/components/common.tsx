import type { SessionRow } from "@runetools/shared";
import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { accountLabel, botLabel, fmtHours, fmtNumber, fmtWhen, statusTone } from "@/lib/format";
import { useAccounts } from "@/lib/queries";
import { cn } from "@/lib/utils";

/**
 * The account filter lives in the URL (?account=Name; ?account= is "Unassigned"; absent
 * is every account) so it survives reloads and moving between pages.
 */
export function useAccountParam(): [string | undefined, (a: string | undefined) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.has("account") ? params.get("account")! : undefined;
  return [value, (a) => setParams((p) => {
    if (a === undefined) p.delete("account"); else p.set("account", a);
    p.delete("page");
    return p;
  }, { replace: true })];
}

const ALL = "\u0000all";

export function AccountFilter() {
  const [account, setAccount] = useAccountParam();
  const accounts = useAccounts();
  const names = accounts.data ? [...accounts.data.accounts.map((a) => a.name), ...accounts.data.orphanNames] : [];
  if (account && !names.includes(account)) names.push(account);
  return (
    <NativeSelect
      aria-label="Account"
      className="w-44"
      value={account ?? ALL}
      onChange={(e) => setAccount(e.target.value === ALL ? undefined : e.target.value)}
    >
      <option value={ALL}>All accounts</option>
      {names.map((n) => <option key={n} value={n}>{n}</option>)}
      {(accounts.data?.hasUnassigned || account === "") && <option value="">Unassigned</option>}
    </NativeSelect>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone = statusTone(status);
  return (
    <Badge variant={tone === "default" ? "default" : tone} className="capitalize">
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
      {status === "crashed" && <AlertTriangle />}
      {status}
    </Badge>
  );
}

export function StatTile({ label, value, sub, className }: { label: string; value: ReactNode; sub?: ReactNode; className?: string }) {
  return (
    <Card className={cn("gap-1 px-5 py-4", className)}>
      <div className="text-muted-foreground text-sm">{label}</div>
      <div className="text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="text-muted-foreground text-xs">{sub}</div>}
    </Card>
  );
}

export function Swatch({ color, className }: { color: string; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2.5 shrink-0 rounded-[3px]", className)} style={{ background: color }} />;
}

export function SessionsTable({ rows, now, showAccount = true, empty = "No sessions yet." }: {
  rows: SessionRow[]; now?: string; showAccount?: boolean; empty?: string;
}) {
  if (rows.length === 0) return <p className="text-muted-foreground px-2 py-6 text-center text-sm">{empty}</p>;
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Started</TableHead>
          <TableHead>Bot</TableHead>
          {showAccount && <TableHead>Account</TableHead>}
          <TableHead className="text-right">Active</TableHead>
          <TableHead className="text-right">Runs</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="w-full">Reason</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((s) => (
          <TableRow key={s.id} className="relative">
            <TableCell className="tabular-nums">
              <Link to={`/sessions/${s.id}`} className="after:absolute after:inset-0 hover:underline">{fmtWhen(s.startedAt, now)}</Link>
            </TableCell>
            <TableCell>{botLabel(s.bot)}</TableCell>
            {showAccount && <TableCell className={cn(!s.account && "text-muted-foreground")}>{accountLabel(s.account)}</TableCell>}
            <TableCell className="text-right tabular-nums">{fmtHours(s.activeSeconds / 3600)}</TableCell>
            <TableCell className="text-right tabular-nums">{fmtNumber(s.runs)}</TableCell>
            <TableCell><StatusBadge status={s.status} /></TableCell>
            <TableCell className="text-muted-foreground max-w-80 truncate" title={s.reason ?? ""}>
              {s.errors > 0 && <span className="text-destructive mr-2">{s.errors} error{s.errors > 1 ? "s" : ""}</span>}
              {s.reason}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ErrorNote({ error }: { error: Error | null }) {
  if (!error) return null;
  return <p className="text-destructive text-sm">Couldn't load: {error.message}</p>;
}
