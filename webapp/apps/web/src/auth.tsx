import type { Me } from "@runetools/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, setCsrf, setOnUnauthorized } from "@/lib/api";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/api/auth/me"), staleTime: Infinity });
}

/** Renders children only for a logged-in user; otherwise the first-run setup or login form. */
export function AuthGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const me = useMe();

  useEffect(() => {
    setOnUnauthorized(() => qc.invalidateQueries({ queryKey: ["me"] }));
  }, [qc]);

  if (me.data?.state === "authenticated") setCsrf(me.data.csrf);

  if (me.isPending) return null;
  if (me.isError) return <Centered><Alert variant="destructive"><AlertDescription>Can't reach the server: {me.error.message}</AlertDescription></Alert></Centered>;
  if (me.data.state === "setup") return <Centered><LoginForm setup /></Centered>;
  if (me.data.state === "anonymous") return <Centered><LoginForm /></Centered>;
  return <>{children}</>;
}

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex min-h-svh items-center justify-center p-6"><div className="w-full max-w-sm">{children}</div></div>;
}

function LoginForm({ setup = false }: { setup?: boolean }) {
  const qc = useQueryClient();
  const [username, setUsername] = useState(setup ? "admin" : "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const submit = useMutation({
    mutationFn: () => {
      if (setup && password !== confirm) throw new Error("passwords don't match");
      return api.post(setup ? "/api/auth/setup" : "/api/auth/login", { username, password });
    },
    onSuccess: () => qc.resetQueries(),
  });
  const onSubmit = (e: FormEvent) => { e.preventDefault(); submit.mutate(); };

  return (
    <Card>
      <CardHeader className="flex-col">
        <CardTitle className="text-xl">{setup ? "Welcome to RuneTools" : "RuneTools"}</CardTitle>
        <CardDescription>{setup ? "Create the login for this dashboard." : "Log in to continue."}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="username">Username</Label>
            <Input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus={!setup} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete={setup ? "new-password" : "current-password"} value={password}
              onChange={(e) => setPassword(e.target.value)} required minLength={setup ? 8 : 1} autoFocus={setup} />
          </div>
          {setup && (
            <div className="grid gap-2">
              <Label htmlFor="confirm">Repeat password</Label>
              <Input id="confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </div>
          )}
          {submit.isError && <p className="text-destructive text-sm">{submit.error.message}</p>}
          <Button type="submit" disabled={submit.isPending}>{setup ? "Create login" : "Log in"}</Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => api.post("/api/auth/logout"), onSuccess: () => qc.resetQueries() });
}
