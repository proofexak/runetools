import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Power, Server } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { botView } from "@/lib/bot-control";
import { keys, useAccounts, useBotStatus } from "@/lib/queries";
import { cn } from "@/lib/utils";

/**
 * The bot container (PRO-90): start it and its manual mode (RuneLite + the bot menu), stop
 * it, and go to the live view. Picking and driving a bot happens there, by hand.
 * `watchLink` false on the account page itself, which shows the live view right below.
 */
export function BotControlCard({ watchLink = true }: { watchLink?: boolean }) {
  const qc = useQueryClient();
  const status = useBotStatus();
  const accounts = useAccounts();
  const [confirmStop, setConfirmStop] = useState(false);
  const act = useMutation({
    mutationFn: (action: "start" | "stop") => api.post(`/api/bot/${action}`),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.bot }),
  });

  if (!status.data?.enabled) return null;          // no docker proxy here: nothing to control
  const v = botView(status.data);
  const active = accounts.data?.accounts.find((a) => a.active);

  return (
    <Card className="gap-3" data-testid="bot-control">
      <CardHeader className="items-center">
        <div className="grid gap-1.5">
          <CardTitle className="flex items-center gap-2"><Server className="size-4" /> Bot container</CardTitle>
          <CardDescription className={cn("flex items-center gap-2", v.tone === "problem" && "text-destructive")}>
            {v.tone === "busy" && <Loader2 className="size-3.5 animate-spin" />}
            {v.headline}
          </CardDescription>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {v.canStart && (
            <Button size="sm" disabled={act.isPending} onClick={() => act.mutate("start")}><Play /> Start</Button>
          )}
          {watchLink && v.watchable && (active
            ? <Button asChild size="sm" variant="outline"><Link to={`/accounts/${active.id}?watch=1`}>Watch live</Link></Button>
            : <span className="text-muted-foreground text-xs">Set an active account to watch it live</span>)}
          {v.canStop && (
            <Button size="sm" variant="ghost" disabled={act.isPending} onClick={() => setConfirmStop(true)}>
              <Power /> Stop
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="grid gap-2">
        <div className="flex flex-wrap gap-2">
          {v.rows.map((r) => (
            <Badge key={r.label} variant={r.on ? "success" : "muted"}>{r.label}: {r.value}</Badge>
          ))}
        </div>
        {(v.error || act.error) && <p className="text-destructive text-sm">{v.error ?? act.error?.message}</p>}
      </CardContent>

      {confirmStop && (
        <Dialog open onOpenChange={(o) => !o && setConfirmStop(false)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Stop the bot container?</DialogTitle>
              <DialogDescription>
                A running bot ends its session first (up to 30 s), then RuneLite and the menu close.
                The container stays — Start wakes it again.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmStop(false)}>Cancel</Button>
              <Button variant="destructive" onClick={() => { setConfirmStop(false); act.mutate("stop"); }}>Stop</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
}
