"use client";

import { useState } from "react";
import { commandSummary } from "@/components/CommandButtons";
import { useCommand } from "@/lib/useCommand";

export function PluginEditor({ accountId, plugin, enabled, config }: {
  accountId: string; plugin: string; enabled: boolean; config: Record<string, unknown>;
}) {
  const { send, cmd, error, busy } = useCommand();
  const [on, setOn] = useState(enabled);
  const [text, setText] = useState(JSON.stringify(config, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    let parsed: unknown;
    try { parsed = JSON.parse(text || "{}"); } catch { setParseError("JSON inválido"); return; }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) { setParseError("a config precisa ser um objeto { }"); return; }
    setParseError(null);
    void send(accountId, "plugin.set", { plugin, enabled: on, config: parsed });
  }

  return (
    <form onSubmit={submit} className="card stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>{plugin}</h2>
        <label className="row" style={{ display: "flex" }}>
          <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} /> ligado
        </label>
      </div>
      <label>Config (JSON)<textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} /></label>
      {(parseError || error) && <p className="error">{parseError ?? error}</p>}
      {cmd && <p className={`small ${cmd.status === "failed" ? "error" : "muted"}`}>{commandSummary(cmd)}</p>}
      <div><button type="submit" disabled={busy}>{busy ? "Enviando…" : "Salvar e aplicar"}</button></div>
      <p className="muted small" style={{ margin: 0 }}>O worker valida a config antes de gravar. Se a sessão estiver conectada, o plugin reinicia na hora.</p>
    </form>
  );
}
