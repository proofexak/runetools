import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useSearchParams } from "react-router";
import { AccountFilter, ErrorNote, SessionsTable, useAccountParam } from "@/components/common";
import { PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { botLabel } from "@/lib/format";
import { useSessions } from "@/lib/queries";
import { cn } from "@/lib/utils";

const PAGE = 50;
const STATUSES = ["running", "done", "stopped", "crashed", "killed", "interrupted"];

export function SessionsPage() {
  const [params, setParams] = useSearchParams();
  const [account] = useAccountParam();
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const filters = {
    bot: params.get("bot") || undefined,
    status: params.get("status") || undefined,
    from: params.get("from") || undefined,
    to: params.get("to") || undefined,
  };
  const q = useSessions({ account, ...filters, limit: PAGE, offset: page * PAGE });

  const set = (key: string, value: string | undefined) => setParams((p) => {
    if (value) p.set(key, value); else p.delete(key);
    if (key !== "page") p.delete("page");
    return p;
  }, { replace: true });

  const total = q.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const filtered = Object.values(filters).some(Boolean) || account !== undefined;

  return (
    <>
      <PageHeader title="Sessions" description={q.data ? `${total} session${total === 1 ? "" : "s"}` : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <AccountFilter />
        <NativeSelect aria-label="Bot" className="w-40" value={filters.bot ?? ""} onChange={(e) => set("bot", e.target.value)}>
          <option value="">All bots</option>
          {q.data?.bots.map((b) => <option key={b} value={b}>{botLabel(b)}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Status" className="w-36" value={filters.status ?? ""} onChange={(e) => set("status", e.target.value)}>
          <option value="">Any status</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </NativeSelect>
        <Input aria-label="From" type="date" className="w-40" value={filters.from ?? ""} onChange={(e) => set("from", e.target.value)} />
        <span className="text-muted-foreground text-sm">to</span>
        <Input aria-label="To" type="date" className="w-40" value={filters.to ?? ""} onChange={(e) => set("to", e.target.value)} />
        {filtered && (
          <Button variant="ghost" size="sm" onClick={() => setParams({}, { replace: true })}><X /> Clear</Button>
        )}
      </div>
      <ErrorNote error={q.error} />
      <Card className="py-2">
        <CardContent className={cn("px-3 transition-opacity", q.isPlaceholderData && "opacity-60")}>
          {q.data ? (
            <SessionsTable rows={q.data.sessions} empty={filtered ? "No sessions match these filters." : "No sessions logged yet."} />
          ) : (
            <div className="grid gap-2 py-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-8" />)}</div>
          )}
        </CardContent>
      </Card>
      {pages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">Page {page + 1} of {pages}</span>
          <Button variant="outline" size="icon-sm" disabled={page === 0} onClick={() => set("page", String(page - 1))} aria-label="Previous page"><ChevronLeft /></Button>
          <Button variant="outline" size="icon-sm" disabled={page + 1 >= pages} onClick={() => set("page", String(page + 1))} aria-label="Next page"><ChevronRight /></Button>
        </div>
      )}
    </>
  );
}
