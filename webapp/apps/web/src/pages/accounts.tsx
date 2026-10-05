import type { Account } from "@runetools/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Info, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ErrorNote } from "@/components/common";
import { PageHeader } from "@/components/layout";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoginCell, VaultCard } from "@/components/vault";
import { api } from "@/lib/api";
import { keys, useAccounts } from "@/lib/queries";

const NONE = "\u0000none";

export function AccountsPage() {
  const qc = useQueryClient();
  const accounts = useAccounts();
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const [deleting, setDeleting] = useState<Account | null>(null);
  const [prefill, setPrefill] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: keys.accounts });

  const activate = useMutation({
    mutationFn: (id: number | null) => api.post(id === null ? "/api/accounts/deactivate" : `/api/accounts/${id}/activate`),
    onSuccess: refresh,
  });

  const data = accounts.data;
  const active = data?.accounts.find((a) => a.active);

  return (
    <>
      <PageHeader title="Accounts" description="Who the bots are playing on, and their logins">
        <Button onClick={() => { setPrefill(""); setEditing("new"); }}><Plus /> Add account</Button>
      </PageHeader>
      <ErrorNote error={accounts.error ?? activate.error} />
      {data && (
        <div className="grid grid-cols-1 gap-4">
          <Card>
            <CardHeader>
              <div className="grid gap-1.5">
                <CardTitle>New sessions are logged to</CardTitle>
                <CardDescription>
                  Every bot session started on this machine is tagged with this account (written to data/active_account).
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3">
              <NativeSelect aria-label="Active account" className="max-w-xs" value={active ? String(active.id) : NONE}
                disabled={activate.isPending}
                onChange={(e) => activate.mutate(e.target.value === NONE ? null : Number(e.target.value))}>
                <option value={NONE}>No account (unassigned)</option>
                {data.accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </NativeSelect>
              {data.envOverride && (
                <Alert>
                  <Info />
                  <AlertDescription>
                    RUNETOOLS_ACCOUNT is set to <b>{data.envOverride}</b> for this server: bots started with that variable
                    (e.g. one container per account) ignore this choice.
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card className="gap-2">
            <CardHeader><CardTitle>Accounts</CardTitle></CardHeader>
            <CardContent className="px-3">
              {data.accounts.length === 0 ? (
                <p className="text-muted-foreground px-2 py-6 text-center text-sm">No accounts yet. Add one to start tagging sessions.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>Name</TableHead>
                      <TableHead>Notes</TableHead>
                      <TableHead className="w-full">Login</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.accounts.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="font-medium">
                          <span className="flex items-center gap-2">{a.name}{a.active && <Badge variant="success">active</Badge>}</span>
                        </TableCell>
                        <TableCell className="text-muted-foreground max-w-60 truncate" title={a.notes}>{a.notes || "—"}</TableCell>
                        <TableCell><LoginCell account={a} /></TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" size="icon-sm" aria-label={`Edit ${a.name}`} onClick={() => setEditing(a)}><Pencil /></Button>
                            <Button variant="ghost" size="icon-sm" aria-label={`Delete ${a.name}`} onClick={() => setDeleting(a)}><Trash2 /></Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              {data.orphanNames.length > 0 && (
                <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-2 border-t px-2 pt-3 text-sm">
                  In the logs but not an account:
                  {data.orphanNames.map((n) => (
                    <Button key={n} variant="outline" size="sm" onClick={() => { setPrefill(n); setEditing("new"); }}>
                      <Plus /> {n}
                    </Button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <VaultCard />
        </div>
      )}
      {editing && <AccountDialog account={editing === "new" ? null : editing} prefill={prefill} onClose={() => setEditing(null)} />}
      {deleting && <DeleteDialog account={deleting} onClose={() => setDeleting(null)} />}
    </>
  );
}

function AccountDialog({ account, prefill, onClose }: { account: Account | null; prefill: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(account?.name ?? prefill);
  const [notes, setNotes] = useState(account?.notes ?? "");
  const save = useMutation({
    mutationFn: () => account ? api.patch(`/api/accounts/${account.id}`, { name, notes }) : api.post("/api/accounts", { name, notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.accounts });
      if (account && name !== account.name) qc.invalidateQueries();   // history was re-tagged
      onClose();
    },
  });
  const onSubmit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{account ? `Edit ${account.name}` : "Add account"}</DialogTitle>
          <DialogDescription>
            {account ? "Renaming moves this account's session history to the new name." : "Use the in-game name, so the sessions read clearly."}
          </DialogDescription>
        </DialogHeader>
        <form id="account-form" onSubmit={onSubmit} className="grid gap-3">
          <div className="grid gap-2">
            <Label htmlFor="aname">Name</Label>
            <Input id="aname" value={name} maxLength={32} onChange={(e) => setName(e.target.value)} required autoFocus />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="anotes">Notes</Label>
            <Textarea id="anotes" value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} />
          </div>
          {save.isError && <p className="text-destructive text-sm">{save.error.message}</p>}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="account-form" disabled={save.isPending}>{account ? "Save" : "Add"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.delete(`/api/accounts/${account.id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: keys.accounts }); onClose(); },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {account.name}?</DialogTitle>
          <DialogDescription>
            {account.hasLogin ? "Its stored login is deleted too. " : ""}
            Logged sessions stay and keep the name.{account.active ? " New sessions will be logged without an account." : ""}
          </DialogDescription>
        </DialogHeader>
        {del.isError && <p className="text-destructive text-sm">{del.error.message}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" disabled={del.isPending} onClick={() => del.mutate()}>Delete</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
