import type { Account, LoginEntry } from "@runetools/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Eye, EyeOff, KeyRound, Lock, LockOpen, Pencil, ShieldAlert } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { keys, useVault } from "@/lib/queries";

const entryKey = (id: number) => ["vault-entry", id] as const;

/** Vault state + unlock / first-time setup / lock. */
export function VaultCard() {
  const qc = useQueryClient();
  const vault = useVault();
  const [master, setMaster] = useState("");
  const [confirm, setConfirm] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: keys.vault });

  const unlock = useMutation({
    mutationFn: () => {
      if (!vault.data?.exists && master !== confirm) throw new Error("passwords don't match");
      return api.post(vault.data?.exists ? "/api/vault/unlock" : "/api/vault/setup", { master });
    },
    onSuccess: () => { setMaster(""); setConfirm(""); refresh(); },
  });
  const lock = useMutation({
    mutationFn: () => api.post("/api/vault/lock"),
    onSuccess: () => { qc.removeQueries({ queryKey: ["vault-entry"] }); refresh(); },
  });

  if (!vault.data) return null;
  const { exists, unlocked, autoLockSeconds } = vault.data;
  const onSubmit = (e: FormEvent) => { e.preventDefault(); unlock.mutate(); };

  return (
    <Card>
      <CardHeader>
        <div className="grid gap-1.5">
          <CardTitle className="flex items-center gap-2">
            {unlocked ? <LockOpen className="text-success size-4" /> : <Lock className="size-4" />}
            Login vault
          </CardTitle>
          <CardDescription>
            {!exists && "Email + password per account, encrypted with a master password."}
            {exists && unlocked && `Unlocked. Locks itself after ${Math.round(autoLockSeconds / 60)} minutes without use.`}
            {exists && !unlocked && "Locked. Unlock to see, copy or edit logins."}
          </CardDescription>
        </div>
        {unlocked && <Button variant="outline" size="sm" onClick={() => lock.mutate()}><Lock /> Lock now</Button>}
      </CardHeader>
      {!unlocked && (
        <CardContent>
          <form onSubmit={onSubmit} className="grid max-w-md gap-3">
            {!exists && (
              <Alert variant="warning">
                <ShieldAlert />
                <AlertDescription>
                  The master password is never stored and can't be recovered. If you forget it, the stored logins are lost
                  (you can reset the vault in Settings).
                </AlertDescription>
              </Alert>
            )}
            <div className="grid gap-2">
              <Label htmlFor="master">{exists ? "Master password" : "New master password"}</Label>
              <Input id="master" type="password" autoComplete={exists ? "current-password" : "new-password"}
                value={master} onChange={(e) => setMaster(e.target.value)} required minLength={exists ? 1 : 8} />
            </div>
            {!exists && (
              <div className="grid gap-2">
                <Label htmlFor="master2">Repeat it</Label>
                <Input id="master2" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
              </div>
            )}
            {unlock.isError && <p className="text-destructive text-sm">{unlock.error.message}</p>}
            <div>
              <Button type="submit" disabled={unlock.isPending}>
                <KeyRound /> {unlock.isPending ? "Working…" : exists ? "Unlock" : "Create vault"}
              </Button>
            </div>
          </form>
        </CardContent>
      )}
    </Card>
  );
}

/** One account's stored login, inline in the accounts list. */
export function LoginCell({ account }: { account: Account }) {
  const vault = useVault();
  const unlocked = !!vault.data?.unlocked;
  const [shown, setShown] = useState(false);
  const [editing, setEditing] = useState(false);
  const entry = useQuery({
    queryKey: entryKey(account.id),
    queryFn: () => api.get<LoginEntry>(`/api/vault/entries/${account.id}`),
    enabled: unlocked && account.hasLogin && shown,
    staleTime: Infinity,
    retry: false,
  });
  useEffect(() => { if (!unlocked) setShown(false); }, [unlocked]);

  if (!vault.data?.exists && !account.hasLogin) return <span className="text-muted-foreground text-sm">—</span>;
  if (!unlocked) {
    return <span className="text-muted-foreground flex items-center gap-1.5 text-sm"><Lock className="size-3.5" />{account.hasLogin ? "Stored" : "None"}</span>;
  }
  return (
    <div className="flex flex-wrap items-center gap-1">
      {account.hasLogin && !shown && (
        <Button variant="ghost" size="sm" onClick={() => setShown(true)}><Eye /> Show</Button>
      )}
      {shown && entry.data && (
        <>
          <span className="mr-1 font-mono text-[13px]">{entry.data.email || <span className="text-muted-foreground">no email</span>}</span>
          <CopyButton value={entry.data.email} label="Copy email" />
          <Secret value={entry.data.password} />
          <CopyButton value={entry.data.password} label="Copy password" />
          <Button variant="ghost" size="icon-sm" aria-label="Hide" onClick={() => setShown(false)}><EyeOff /></Button>
        </>
      )}
      {shown && entry.isError && <span className="text-destructive text-sm">{entry.error.message}</span>}
      <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
        <Pencil /> {account.hasLogin ? "Edit" : "Add login"}
      </Button>
      {editing && <LoginDialog account={account} onClose={() => setEditing(false)} />}
    </div>
  );
}

function Secret({ value }: { value: string }) {
  const [visible, setVisible] = useState(false);
  if (!value) return <span className="text-muted-foreground text-sm">no password</span>;
  return (
    <button type="button" className="hover:bg-accent rounded px-1.5 py-0.5 font-mono text-[13px]" onClick={() => setVisible(!visible)}
      title={visible ? "Hide password" : "Show password"}>
      {visible ? value : "•".repeat(Math.min(12, value.length))}
    </button>
  );
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [done, setDone] = useState(false);
  if (!value) return null;
  return (
    <Button variant="ghost" size="icon-sm" aria-label={label} title={label} onClick={async () => {
      await navigator.clipboard.writeText(value);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    }}>
      {done ? <Check className="text-success" /> : <Copy />}
    </Button>
  );
}

function LoginDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const qc = useQueryClient();
  const existing = useQuery({
    queryKey: entryKey(account.id),
    queryFn: () => api.get<LoginEntry>(`/api/vault/entries/${account.id}`),
    enabled: account.hasLogin,
    staleTime: Infinity,
    retry: false,
  });
  const [form, setForm] = useState<LoginEntry | null>(account.hasLogin ? null : { email: "", password: "", notes: "" });
  useEffect(() => { if (existing.data && !form) setForm(existing.data); }, [existing.data, form]);

  const save = useMutation({
    mutationFn: () => api.put(`/api/vault/entries/${account.id}`, form),
    onSuccess: () => {
      qc.setQueryData(entryKey(account.id), form);
      qc.invalidateQueries({ queryKey: keys.accounts });
      onClose();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/api/vault/entries/${account.id}`),
    onSuccess: () => {
      qc.removeQueries({ queryKey: entryKey(account.id) });
      qc.invalidateQueries({ queryKey: keys.accounts });
      onClose();
    },
  });
  const error = save.error ?? remove.error ?? (existing.error instanceof ApiError ? existing.error : null);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Login for {account.name}</DialogTitle>
          <DialogDescription>Stored encrypted. The bots never use it — they log in through RuneLite.</DialogDescription>
        </DialogHeader>
        {!form ? <p className="text-muted-foreground text-sm">Loading…</p> : (
          <form id="login-form" className="grid gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
            <div className="grid gap-2">
              <Label htmlFor="email">Email / username</Label>
              <Input id="email" autoComplete="off" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pw">Password</Label>
              <Input id="pw" type="password" autoComplete="new-password" value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="lnotes">Notes</Label>
              <Textarea id="lnotes" value={form.notes} maxLength={500} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
          </form>
        )}
        {error && <p className="text-destructive text-sm">{error.message}</p>}
        <DialogFooter>
          {account.hasLogin && (
            <Button variant="ghost" className="text-destructive mr-auto" disabled={remove.isPending} onClick={() => remove.mutate()}>
              Remove login
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="login-form" disabled={!form || save.isPending}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
