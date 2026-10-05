import type { Account } from "@runetools/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";

export function AccountDialog({ account, prefill, onClose }: { account: Account | null; prefill: string; onClose: () => void }) {
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

export function DeleteDialog({ account, onClose, onDeleted }: { account: Account; onClose: () => void; onDeleted?: () => void }) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.delete(`/api/accounts/${account.id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: keys.accounts }); onClose(); onDeleted?.(); },
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
