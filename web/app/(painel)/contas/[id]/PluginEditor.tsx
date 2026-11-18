"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
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

  // cada plugin recolhido: a aba Ajustes mostra a lista e só abre o JSON de quem for mexer
  return (
    <details className="fold">
      <summary className="fold-head">
        <span className="fold-title"><code>{plugin}</code></span>
        <span className={`small fold-meta ${enabled ? "good-text" : "muted"}`}>{enabled ? "ligado" : "desligado"}</span>
        <span className="fold-chevron" aria-hidden />
      </summary>
      <form onSubmit={submit} className="fold-body">
        <label className="row" style={{ display: "flex" }}>
          <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} /> ligado
        </label>
        <label>Config (JSON)<textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} /></label>
        {parseError && <p className="error small" style={{ margin: 0 }}>{parseError}</p>}
        <CommandStatus cmd={cmd} error={error} />
        <div><button type="submit" disabled={busy}>{busy ? "Enviando…" : "Salvar e aplicar"}</button></div>
      </form>
    </details>
  );
}
