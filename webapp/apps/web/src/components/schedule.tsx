import type { Account, ScheduleActivity, ScheduleBlock, ScheduleProfile, ScheduleResponse } from "@runetools/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus, RefreshCw, Settings2, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ErrorNote, Swatch } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { botColors } from "@/lib/bots";
import { fmtHours, fmtNumber } from "@/lib/format";
import { useSchedule } from "@/lib/queries";
import {
  addDays, adherence, mondayOf, segments, weekDays, zonedDate, zonedEpoch, zonedSeconds, type Day,
} from "@/lib/schedule";
import { useIsDark } from "@/lib/theme";
import { cn } from "@/lib/utils";

const DEFAULT_TZ = "Europe/Warsaw";
const TICKS = [0, 6, 12, 18, 24];
/** What the bots' menus offer (lib/headless resolves these names; a wrong one is skipped). */
const SUGGESTED: ScheduleActivity[] = [
  ...["Green", "Blue", "Red", "Black"].map((c) => ({ bot: "Tanning", launch: `${c} Dragonhide`, value: "Al Kharid", weight: 1 })),
  { bot: "Choco Grind", launch: "Run", value: "500", weight: 1 },
  { bot: "Mining", launch: "Varrock Exp", value: null, weight: 1 },
  { bot: "Mining", launch: "Golden Nuggets", value: null, weight: 1 },
];

const label = (b: { bot: string | null; launch?: string }) => (b.launch ? `${b.bot} · ${b.launch}` : b.bot ?? "?");
const clock = (tz: string, t: number) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit" }).format(new Date(t * 1000));
const dayName = (date: string) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" })
    .format(new Date(`${date}T12:00:00Z`));

/** An account's play schedule (PRO-102): the week planned vs what ran, adherence, settings. */
export function ScheduleCard({ account }: { account: Account }) {
  const [week, setWeek] = useState(0);
  const [settings, setSettings] = useState(false);
  const [editing, setEditing] = useState<ScheduleBlock | null>(null);
  const [tz, setTz] = useState(DEFAULT_TZ);
  const nowSec = Math.floor(Date.now() / 1000);
  const monday = addDays(mondayOf(zonedDate(tz, nowSec)), 7 * week);
  const days = useMemo(() => weekDays(monday, tz), [monday, tz]);
  const q = useSchedule(account.id, days[0]!.start, days[6]!.end);
  const data = q.data;
  if (data && data.profile.timezone !== tz) setTz(data.profile.timezone);

  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["schedule"] });
  const save = useMutation({
    mutationFn: (p: Omit<ScheduleProfile, "seed">) => api.put(`/api/accounts/${account.id}/schedule`, p),
    onSuccess: refresh,
  });
  const regenerate = useMutation({
    mutationFn: () => api.post(`/api/accounts/${account.id}/schedule/regenerate`),
    onSuccess: refresh,
  });

  const dark = useIsDark();
  const colors = useMemo(() => {
    const names = [...(data?.profile.activities ?? []).map(label), ...(data?.blocks ?? []).map(label)];
    return botColors(names, dark);
  }, [data, dark]);
  const stats = data && adherence(data.blocks, data.actual, days[0]!.start, days[6]!.end, data.now);
  const profile = data?.profile;

  return (
    <Card className="gap-4">
      <CardHeader className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1.5">
          <CardTitle>Schedule</CardTitle>
          <CardDescription>
            {profile?.enabled
              ? `${profile.monthlyHours} h a month, in ${profile.timezone}. The bot follows it with SCHEDULE=1 in docker/accounts/${account.name}.env.`
              : "Off — the bot plays only when started by hand."}
          </CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="icon-sm" aria-label="Previous week" onClick={() => setWeek(week - 1)}><ChevronLeft /></Button>
          <Button variant="outline" size="sm" disabled={week === 0} onClick={() => setWeek(0)}>This week</Button>
          <Button variant="outline" size="icon-sm" aria-label="Next week" onClick={() => setWeek(week + 1)}><ChevronRight /></Button>
          {profile && (
            <>
              <Button size="sm" variant={profile.enabled ? "default" : "outline"} disabled={save.isPending}
                onClick={() => save.mutate({ ...profile, enabled: !profile.enabled })}
                title={profile.activities.length === 0 && !profile.enabled ? "Add an activity in Settings first" : undefined}>
                {profile.enabled ? "On" : "Off"}
              </Button>
              <Button size="sm" variant="outline" disabled={!profile.enabled || regenerate.isPending}
                onClick={() => regenerate.mutate()} title="Draw a new plan from tomorrow (today and blocks edited by hand stay)">
                <RefreshCw /> Regenerate
              </Button>
            </>
          )}
          <Button size="sm" variant={settings ? "secondary" : "outline"} onClick={() => setSettings(!settings)}>
            <Settings2 /> Settings
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        <ErrorNote error={q.error ?? save.error ?? regenerate.error} />
        {settings && profile && (
          <ProfileForm profile={profile} pending={save.isPending}
            onSave={(p) => save.mutate(p, { onSuccess: () => setSettings(false) })} />
        )}
        {stats && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-5">
            <Stat label="Planned" value={fmtHours(stats.plannedHours)} />
            <Stat label="Ran" value={fmtHours(stats.ranHours)} />
            <Stat label="Followed" value={stats.coverage === null ? "—" : `${fmtNumber(stats.coverage * 100)} %`}
              sub="of the plan so far" />
            <Stat label="Outside the plan" value={`${fmtNumber(stats.outsideMinutes)} min`} />
            <Stat label="Missed blocks" value={fmtNumber(stats.missed)} />
          </div>
        )}
        {data ? <WeekGrid data={data} days={days} tz={tz} colors={colors} onEdit={setEditing} /> : <Skeleton className="h-72" />}
        {data && (
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            <span className="flex items-center gap-1.5"><span className="border-foreground/60 inline-block h-2.5 w-4 rounded-[3px] border" /> planned</span>
            <span className="flex items-center gap-1.5"><span className="bg-foreground/60 inline-block h-1.5 w-4 rounded-[2px]" /> ran</span>
            {[...new Set(data.blocks.map(label))].map((n) => (
              <span key={n} className="flex items-center gap-1.5"><Swatch color={colors.get(n) ?? "#898781"} /> {n}</span>
            ))}
            <span>Click a block ahead to move or delete it.</span>
          </div>
        )}
      </CardContent>
      {editing && <BlockDialog block={editing} tz={tz} onClose={() => setEditing(null)} />}
    </Card>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="text-lg font-semibold tracking-tight">{value}</div>
      {sub && <div className="text-muted-foreground text-xs">{sub}</div>}
    </div>
  );
}

function WeekGrid({ data, days, tz, colors, onEdit }: {
  data: ScheduleResponse; days: Day[]; tz: string; colors: Map<string, string>; onEdit: (b: ScheduleBlock) => void;
}) {
  return (
    <div className="grid gap-1 text-xs">
      <div className="text-muted-foreground relative ml-24 h-4">
        {TICKS.map((h) => (
          <span key={h} className="absolute -translate-x-1/2" style={{ left: `${h / 24 * 100}%` }}>{String(h).padStart(2, "0")}</span>
        ))}
      </div>
      {days.map((day) => {
        const today = data.now >= day.start && data.now < day.end;
        return (
          <div key={day.date} className="flex items-center gap-2">
            <div className={cn("w-22 shrink-0 text-right", today ? "font-semibold" : "text-muted-foreground")}>{dayName(day.date)}</div>
            <div className="bg-muted/40 relative h-9 flex-1 overflow-hidden rounded-md">
              {TICKS.slice(1, -1).map((h) => (
                <div key={h} className="bg-border absolute inset-y-0 w-px" style={{ left: `${h / 24 * 100}%` }} />
              ))}
              {segments(data.blocks, day).map(({ left, width, item }) => {
                const c = colors.get(label(item)) ?? "#898781";
                const ahead = item.start > data.now;
                return (
                  <button key={item.id} type="button" disabled={!ahead} onClick={() => onEdit(item)}
                    className={cn("absolute top-1 h-4 rounded-[3px] border-2", ahead ? "cursor-pointer hover:brightness-125" : "cursor-default")}
                    style={{ left: `${left}%`, width: `${width}%`, borderColor: c, background: `${c}26` }}
                    title={`${label(item)}${item.value ? ` (${item.value})` : ""}\n${clock(tz, item.start)}–${clock(tz, item.end)} · ${fmtHours((item.end - item.start) / 3600)}${item.edited ? " · edited" : ""}`} />
                );
              })}
              {segments(data.actual, day).map(({ left, width, item }) => (
                <div key={item.id} className="bg-foreground/60 absolute bottom-1 h-2 rounded-[2px]"
                  style={{ left: `${left}%`, width: `${Math.max(width, 0.3)}%` }}
                  title={`${item.bot ?? "?"} ran ${clock(tz, item.start)}–${clock(tz, item.end)} · ${item.status}`} />
              ))}
              {today && (
                <div className="bg-destructive absolute inset-y-0 w-0.5" title="now"
                  style={{ left: `${(data.now - day.start) / (day.end - day.start) * 100}%` }} />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ProfileForm({ profile, pending, onSave }: {
  profile: ScheduleProfile; pending: boolean; onSave: (p: Omit<ScheduleProfile, "seed">) => void;
}) {
  const [hours, setHours] = useState(String(profile.monthlyHours));
  const [tz, setTz] = useState(profile.timezone);
  const [ramp, setRamp] = useState(profile.rampStart ?? "");
  const [acts, setActs] = useState<ScheduleActivity[]>(profile.activities.length ? profile.activities : [SUGGESTED[0]!]);
  const zones = useMemo(() => {
    try { return Intl.supportedValuesOf("timeZone"); } catch { return [DEFAULT_TZ]; }
  }, []);
  const set = (i: number, patch: Partial<ScheduleActivity>) => setActs(acts.map((a, j) => (j === i ? { ...a, ...patch } : a)));

  return (
    <form className="bg-muted/30 grid gap-4 rounded-lg border p-4" onSubmit={(e) => {
      e.preventDefault();
      onSave({ enabled: profile.enabled, timezone: tz.trim(), monthlyHours: Math.round(Number(hours) || 0),
        rampStart: ramp || null, activities: acts.filter((a) => a.bot.trim() && a.launch.trim()) });
    }}>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-1.5">
          <Label htmlFor="s-hours">Hours a month</Label>
          <Input id="s-hours" type="number" min={0} max={400} value={hours} onChange={(e) => setHours(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="s-tz">Timezone (the proxy's country)</Label>
          <Input id="s-tz" list="s-zones" value={tz} onChange={(e) => setTz(e.target.value)} />
          <datalist id="s-zones">{zones.map((z) => <option key={z} value={z} />)}</datalist>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="s-ramp">Ramp up from (new account)</Label>
          <Input id="s-ramp" type="date" value={ramp} onChange={(e) => setRamp(e.target.value)} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Activities — rotated, the least recently played first; each must start where the others end</Label>
        <datalist id="s-bots">{[...new Set(SUGGESTED.map((s) => s.bot))].map((b) => <option key={b} value={b} />)}</datalist>
        <datalist id="s-launches">{[...new Set(SUGGESTED.map((s) => s.launch))].map((l) => <option key={l} value={l} />)}</datalist>
        {acts.map((a, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_1fr_5rem_auto] items-center gap-2">
            <Input aria-label="Bot" placeholder="Bot" list="s-bots" value={a.bot} onChange={(e) => set(i, { bot: e.target.value })} />
            <Input aria-label="Launch" placeholder="Launch" list="s-launches" value={a.launch} onChange={(e) => set(i, { launch: e.target.value })} />
            <Input aria-label="Value" placeholder="Value (Al Kharid, GE, a number…)" value={a.value ?? ""}
              onChange={(e) => set(i, { value: e.target.value || null })} />
            <Input aria-label="Weight" type="number" min={0} max={100} step="0.5" value={a.weight}
              onChange={(e) => set(i, { weight: Number(e.target.value) || 0 })} />
            <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove" onClick={() => setActs(acts.filter((_, j) => j !== i))}>
              <Trash2 />
            </Button>
          </div>
        ))}
        <div>
          <Button type="button" variant="outline" size="sm" onClick={() => setActs([...acts, { bot: "", launch: "", value: null, weight: 1 }])}>
            <Plus /> Activity
          </Button>
        </div>
      </div>
      <div className="flex justify-end">
        <Button type="submit" disabled={pending}>Save — plans the next 14 days again</Button>
      </div>
    </form>
  );
}

function BlockDialog({ block, tz, onClose }: { block: ScheduleBlock; tz: string; onClose: () => void }) {
  const qc = useQueryClient();
  const date = zonedDate(tz, block.start);
  const hhmm = (t: number) => { const s = zonedSeconds(tz, t); return `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}`; };
  const [start, setStart] = useState(hhmm(block.start));
  const [end, setEnd] = useState(hhmm(block.end));
  const secs = (v: string) => { const [h, m] = v.split(":").map(Number); return (h ?? 0) * 3600 + (m ?? 0) * 60; };
  const done = () => { qc.invalidateQueries({ queryKey: ["schedule"] }); onClose(); };
  const save = useMutation({
    mutationFn: () => {
      const s = zonedEpoch(tz, date, secs(start));
      let e = zonedEpoch(tz, date, secs(end));
      if (e <= s) e = zonedEpoch(tz, addDays(date, 1), secs(end));      // past midnight
      return api.patch(`/api/schedule/blocks/${block.id}`, { start: s, end: e });
    },
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: () => api.delete(`/api/schedule/blocks/${block.id}`), onSuccess: done });

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{label(block)}{block.value ? ` (${block.value})` : ""}</DialogTitle>
        </DialogHeader>
        <div className="text-muted-foreground text-sm">{dayName(date)}, times in {tz}. An edited block stays when the plan is regenerated.</div>
        <div className="grid grid-cols-2 gap-4">
          <div className="grid gap-1.5"><Label htmlFor="b-start">Start</Label>
            <Input id="b-start" type="time" value={start} onChange={(e) => setStart(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label htmlFor="b-end">End</Label>
            <Input id="b-end" type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        </div>
        <ErrorNote error={save.error ?? remove.error} />
        <DialogFooter>
          <Button variant="outline" disabled={remove.isPending} onClick={() => remove.mutate()}><Trash2 /> Delete</Button>
          <Button disabled={save.isPending} onClick={() => save.mutate()}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
