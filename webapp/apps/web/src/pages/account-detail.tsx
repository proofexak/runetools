import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { AccountDialog, DeleteDialog } from "@/components/account-dialogs";
import { BotControlCard } from "@/components/bot-control";
import { ErrorNote } from "@/components/common";
import { PageHeader } from "@/components/layout";
import { LiveView } from "@/components/live-view";
import { LiveSessions, OverviewSkeleton, OverviewView } from "@/components/overview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { LoginCell, VaultCard } from "@/components/vault";
import { api } from "@/lib/api";
import { botView } from "@/lib/bot-control";
import { keys, useAccounts, useBotStatus, useLiveControl, useOverview, useVault } from "@/lib/queries";

/** One account: its stats (the dashboard, filtered), its login and its actions. */
export function AccountDetailPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const accounts = useAccounts();
  const account = accounts.data?.accounts.find((a) => a.id === id);
  const overview = useOverview(account?.name, { enabled: !!account });
  const ready = !!overview.data && !overview.isPlaceholderData;
  // the bot's screen belongs to the account whose session is running (or to whoever holds control)
  const control = useLiveControl();
  // the bot container tags new sessions with the active account: its screen belongs here
  const bot = useBotStatus();
  const botUp = !!account?.active && !!bot.data?.enabled && botView(bot.data).watchable;
  const showScreen = (ready && overview.data!.live.length > 0) || !!control.data?.held || botUp;
  const [params] = useSearchParams();
  const vault = useVault();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const activate = useMutation({
    mutationFn: () => api.post(`/api/accounts/${id}/activate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.accounts }),
  });

  const back = (
    <Button asChild variant="ghost" size="sm" className="text-muted-foreground mb-2 -ml-2">
      <Link to="/accounts"><ArrowLeft /> Accounts</Link>
    </Button>
  );

  if (accounts.data && !account) {
    return (
      <>
        {back}
        <PageHeader title="No such account" description="It may have been deleted." />
      </>
    );
  }

  return (
    <>
      {back}
      <ErrorNote error={accounts.error ?? overview.error ?? activate.error} />
      {account && (
        <>
          <PageHeader title={account.name} description={account.notes || undefined}>
            {account.active
              ? <Badge variant="success" title="New bot sessions are tagged with this account">active</Badge>
              : <Button variant="outline" size="sm" disabled={activate.isPending} onClick={() => activate.mutate()}>Set active</Button>}
            <Button asChild variant="outline" size="sm">
              <Link to={`/bots?account=${encodeURIComponent(account.name)}`}><BarChart3 /> Bot stats</Link>
            </Button>
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil /> Edit</Button>
            <Button variant="outline" size="sm" onClick={() => setDeleting(true)}><Trash2 /> Delete</Button>
          </PageHeader>

          <div className="grid grid-cols-1 gap-4">
            {/* what this account's bot is doing right now, first: state, time in it, paused */}
            {ready
              ? <LiveSessions o={overview.data!} account={account.name} />
              : <Skeleton className="h-14" />}
            {/* the active account's bot container: start / stop it (PRO-90) */}
            {account.active && <BotControlCard watchLink={false} />}
            {/* then its screen, behind "Watch live" (?watch=1 from the dashboard opens it) */}
            {showScreen && <LiveView key={account.id} watch={params.get("watch") === "1"} />}
            <Card className="gap-3">
              <CardHeader>
                <div className="grid gap-1.5">
                  <CardTitle>Login</CardTitle>
                  <CardDescription>
                    {vault.data?.unlocked
                      ? "From the vault. The bots don't use it — they log in through RuneLite."
                      : vault.data?.exists
                        ? "Unlock the vault below to see, copy or edit it."
                        : <>No vault yet: set a master password on the <Link to="/accounts" className="underline">Accounts</Link> page first.</>}
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent><LoginCell account={account} /></CardContent>
            </Card>
            {vault.data?.exists && !vault.data.unlocked && <VaultCard />}

            {/* never show another account's numbers (keepPreviousData) while this one's load */}
            {overview.data && !overview.isPlaceholderData
              ? <OverviewView o={overview.data} account={account.name} live={false} />
              : <OverviewSkeleton />}
          </div>
        </>
      )}
      {editing && account && <AccountDialog account={account} prefill="" onClose={() => setEditing(false)} />}
      {deleting && account && (
        <DeleteDialog account={account} onClose={() => setDeleting(false)} onDeleted={() => navigate("/accounts")} />
      )}
    </>
  );
}
