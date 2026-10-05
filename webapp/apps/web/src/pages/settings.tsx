import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { keys, useSettings, useVault } from "@/lib/queries";

export function SettingsPage() {
  const vault = useVault();
  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid max-w-2xl grid-cols-1 gap-4">
        <LogRootsCard />
        <PasswordCard
          title="App password"
          description="The login for this dashboard. Changing it logs out every other browser."
          url="/api/auth/password"
        />
        {vault.data?.exists && (
          <>
            <PasswordCard
              title="Vault master password"
              description="Re-encrypts every stored login with the new password."
              url="/api/vault/master"
            />
            <ResetVaultCard />
          </>
        )}
      </div>
    </>
  );
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <div className="grid gap-1.5">
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function LogRootsCard() {
  const qc = useQueryClient();
  const settings = useSettings();
  const [text, setText] = useState("");
  useEffect(() => { if (settings.data) setText(settings.data.logRoots.join("\n")); }, [settings.data]);
  const save = useMutation({
    mutationFn: () => api.put("/api/settings", { logRoots: text.split("\n").map((s) => s.trim()).filter(Boolean) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.settings }),
  });
  return (
    <Section
      title="Watched log directories"
      description="Folders holding the bots (each <bot>/log/*.jsonl is read). One per line; the first is the main one — the repo."
    >
      <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Textarea aria-label="Log directories" className="font-mono text-[13px]" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        {settings.data && (
          <p className="text-muted-foreground text-xs">Default: {settings.data.defaultLogRoots.join(", ")} (LOG_ROOTS)</p>
        )}
        {save.isError && <p className="text-destructive text-sm">{save.error.message}</p>}
        {save.isSuccess && !save.isPending && <p className="text-success text-sm">Saved — reading them now.</p>}
        <div><Button type="submit" disabled={save.isPending}>Save</Button></div>
      </form>
    </Section>
  );
}

function PasswordCard({ title, description, url }: { title: string; description: string; url: string }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => {
      if (next !== confirm) throw new Error("new passwords don't match");
      return api.post(url, { current, next });
    },
    onSuccess: () => {
      setCurrent(""); setNext(""); setConfirm("");
      qc.invalidateQueries({ queryKey: keys.vault });
    },
  });
  const id = url.replaceAll("/", "-");
  const onSubmit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };
  return (
    <Section title={title} description={description}>
      <form className="grid gap-3 sm:grid-cols-3" onSubmit={onSubmit}>
        <div className="grid gap-2">
          <Label htmlFor={`${id}-cur`}>Current</Label>
          <Input id={`${id}-cur`} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`${id}-new`}>New</Label>
          <Input id={`${id}-new`} type="password" autoComplete="new-password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required />
        </div>
        <div className="grid gap-2">
          <Label htmlFor={`${id}-rep`}>Repeat new</Label>
          <Input id={`${id}-rep`} type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        </div>
        <div className="flex items-center gap-3 sm:col-span-3">
          <Button type="submit" disabled={save.isPending}>Change</Button>
          {save.isError && <span className="text-destructive text-sm">{save.error.message}</span>}
          {save.isSuccess && <span className="text-success text-sm">Changed.</span>}
        </div>
      </form>
    </Section>
  );
}

function ResetVaultCard() {
  const qc = useQueryClient();
  const [password, setPassword] = useState("");
  const [sure, setSure] = useState(false);
  const reset = useMutation({
    mutationFn: () => api.post("/api/vault/reset", { password }),
    onSuccess: () => { setPassword(""); setSure(false); qc.invalidateQueries(); },
  });
  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <div className="grid gap-1.5">
          <CardTitle>Reset the vault</CardTitle>
          <CardDescription>
            Forgot the master password? This deletes every stored login so you can start over. It can't be undone.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form className="grid max-w-sm gap-3" onSubmit={(e) => { e.preventDefault(); reset.mutate(); }}>
          <div className="grid gap-2">
            <Label htmlFor="reset-pw">App password</Label>
            <Input id="reset-pw" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} />
            Delete all stored logins
          </label>
          {reset.isError && <p className="text-destructive text-sm">{reset.error.message}</p>}
          <div><Button type="submit" variant="destructive" disabled={!sure || reset.isPending}>Reset vault</Button></div>
        </form>
      </CardContent>
    </Card>
  );
}
