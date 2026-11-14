"use client";

import { useState } from "react";
import { PluginEditor } from "./PluginEditor";

export function NewPlugin({ accountId, existing }: { accountId: string; existing: string[] }) {
  const [name, setName] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  if (open) return <PluginEditor accountId={accountId} plugin={open} enabled config={{}} />;
  return (
    <form className="card row" onSubmit={(e) => { e.preventDefault(); if (name.trim()) setOpen(name.trim()); }}>
      <label style={{ flex: 1 }}>Adicionar plugin
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="restock" list="plugins-known" />
      </label>
      <datalist id="plugins-known">
        {["restock", "rank"].filter((p) => !existing.includes(p)).map((p) => <option key={p} value={p} />)}
      </datalist>
      <button className="ghost" type="submit" style={{ alignSelf: "end" }}>Configurar</button>
    </form>
  );
}
