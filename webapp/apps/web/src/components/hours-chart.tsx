/**
 * Hours per day, stacked by bot. Bars ≤ 24 px, 4 px rounded cap on each day's top segment
 * only, 2 px surface gap between segments, hairline grid; legend always shown (≥ 2 bots),
 * hover tooltip, and a table view — the light palette has slots under 3:1 contrast.
 */
import type { DayRow } from "@runetools/shared";
import { BarChart3, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import { Swatch } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { botColors } from "@/lib/bots";
import { botLabel, fmtDay, fmtHours } from "@/lib/format";
import { useAllBots } from "@/lib/queries";
import { useIsDark } from "@/lib/theme";

const GAP = 2;
const RADIUS = 4;

interface Datum { date: string; total: number; top: string | null; [bot: string]: number | string | null }

function segmentPath(x: number, y: number, w: number, h: number, round: boolean): string {
  const r = round ? Math.min(RADIUS, h, w / 2) : 0;
  return `M${x},${y + h}V${y + r}${r ? `Q${x},${y} ${x + r},${y}` : ""}H${x + w - r}` +
    `${r ? `Q${x + w},${y} ${x + w},${y + r}` : ""}V${y + h}Z`;
}

export function HoursChart({ days }: { days: DayRow[] }) {
  const [asTable, setAsTable] = useState(false);
  const dark = useIsDark();
  const allBots = useAllBots();

  const bots = useMemo(() => {
    const seen = new Set<string>();
    for (const d of days) for (const [b, h] of Object.entries(d.bots)) if (h > 0) seen.add(b);
    return [...seen].sort();
  }, [days]);
  const colors = useMemo(() => botColors([...(allBots.data ?? []), ...bots], dark), [allBots.data, bots, dark]);

  const data: Datum[] = useMemo(() => days.map((d) => {
    const row: Datum = { date: d.date, total: d.hours, top: null };
    for (const b of bots) {
      row[b] = d.bots[b] ?? 0;
      if ((d.bots[b] ?? 0) > 0) row.top = b;      // last stacked = drawn on top
    }
    return row;
  }), [days, bots]);

  const max = Math.max(0, ...days.map((d) => d.hours));
  const empty = max === 0;

  return (
    <div className="grid gap-3">
      <div className="flex min-h-8 flex-wrap items-center gap-x-4 gap-y-1">
        {bots.map((b) => (
          <span key={b} className="text-muted-foreground flex items-center gap-1.5 text-xs">
            <Swatch color={colors.get(b)!} />
            {botLabel(b)}
          </span>
        ))}
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setAsTable(!asTable)} aria-pressed={asTable}>
          {asTable ? <BarChart3 /> : <Table2 />}
          {asTable ? "Chart" : "Table"}
        </Button>
      </div>

      {asTable ? (
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Day</TableHead>
              {bots.map((b) => <TableHead key={b} className="text-right">{botLabel(b)}</TableHead>)}
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="text-right">Runs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...days].reverse().map((d) => (
              <TableRow key={d.date}>
                <TableCell>{fmtDay(d.date, true)}</TableCell>
                {bots.map((b) => <TableCell key={b} className="text-right tabular-nums">{d.bots[b] ? fmtHours(d.bots[b]) : "–"}</TableCell>)}
                <TableCell className="text-right font-medium tabular-nums">{d.hours ? fmtHours(d.hours) : "–"}</TableCell>
                <TableCell className="text-right tabular-nums">{Math.round(d.runs) || "–"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div className="relative h-64">
          {empty && (
            <p className="text-muted-foreground absolute inset-0 z-10 flex items-center justify-center text-sm">
              No bot time in the last 14 days.
            </p>
          )}
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: -8 }} barCategoryGap="20%">
              <CartesianGrid vertical={false} stroke="var(--border)" strokeWidth={1} />
              <XAxis
                dataKey="date"
                tickFormatter={(d: string) => fmtDay(d).replace(/^\w+ /, "")}
                tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: "var(--input)" }}
                interval="preserveStartEnd"
                minTickGap={8}
              />
              <YAxis
                tickFormatter={(h: number) => `${h}h`}
                tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
                domain={[0, empty ? 4 : "auto"]}
                width={40}
              />
              <Tooltip cursor={{ fill: "var(--accent)", opacity: 0.6 }} content={(p) => <ChartTooltip {...p} bots={bots} colors={colors} />} />
              {bots.map((b) => (
                <Bar
                  key={b}
                  dataKey={b}
                  stackId="hours"
                  fill={colors.get(b)}
                  maxBarSize={24}
                  isAnimationActive={false}
                  shape={(props: unknown) => {
                    const { x, y, width, height, payload, fill } = props as {
                      x: number; y: number; width: number; height: number; payload: Datum; fill: string;
                    };
                    if (!height || height <= 0) return <g />;
                    const top = payload.top === b;
                    // the surface gap sits on top of every segment that has another above it
                    const h = top ? height : Math.max(0, height - GAP);
                    const yy = top ? y : y + GAP;
                    return <path d={segmentPath(x, yy, width, h, top)} fill={fill} />;
                  }}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function ChartTooltip({ active, payload, bots, colors }: Pick<TooltipContentProps<ValueType, NameType>, "active" | "payload"> & { bots: string[]; colors: Map<string, string> }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]!.payload as Datum;
  const rows = bots.filter((b) => (d[b] as number) > 0).reverse();
  return (
    <div className="bg-popover text-popover-foreground grid min-w-40 gap-1.5 rounded-lg border px-3 py-2 text-xs shadow-md">
      <div className="flex justify-between gap-4 font-medium">
        <span>{fmtDay(d.date, true)}</span>
        <span className="tabular-nums">{d.total ? fmtHours(d.total) : "–"}</span>
      </div>
      {rows.map((b) => (
        <div key={b} className="text-muted-foreground flex items-center gap-2">
          <Swatch color={colors.get(b)!} />
          <span>{botLabel(b)}</span>
          <span className="text-foreground ml-auto tabular-nums">{fmtHours(d[b] as number)}</span>
        </div>
      ))}
    </div>
  );
}
