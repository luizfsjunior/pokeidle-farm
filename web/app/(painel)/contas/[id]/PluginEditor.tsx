"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { PLUGIN_INFO } from "@/lib/plugins";
import { useCommand } from "@/lib/useCommand";

export function PluginEditor({ accountId, plugin, enabled, config }: {
  accountId: string; plugin: string; enabled: boolean; config: Record<string, unknown>;
}) {
  const { send, cmd, error, busy } = useCommand();
  const [text, setText] = useState(JSON.stringify(config, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);
  const info = PLUGIN_INFO[plugin];

  function save(e: React.FormEvent) {
    e.preventDefault();
    let parsed: unknown;
    try { parsed = JSON.parse(text || "{}"); } catch { setParseError("JSON inválido"); return; }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) { setParseError("a config precisa ser um objeto { }"); return; }
    setParseError(null);
    void send(accountId, "plugin.set", { plugin, enabled, config: parsed });
  }

  return (
    <div className="plugin-row">
      <div className="plugin-head">
        <span>
          <strong>{info?.label ?? plugin}</strong> <code className="small muted">{plugin}</code>
          <span className="small muted plugin-hint">{info?.hint}{info?.managed && <> Ajuste pelo {info.managed}.</>}</span>
        </span>
        <label className="row plugin-toggle">
          <input type="checkbox" role="switch" checked={enabled} disabled={busy}
            onChange={(e) => void send(accountId, "plugin.set", { plugin, enabled: e.target.checked })} />
          {enabled ? <span className="good-text small">ligado</span> : <span className="muted small">desligado</span>}
        </label>
      </div>
      <details className="plugin-advanced">
        <summary className="small muted">Avançado (config em JSON)</summary>
        <form onSubmit={save} className="stack">
          <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label={`Config de ${plugin}`} />
          {parseError && <p className="error small" style={{ margin: 0 }}>{parseError}</p>}
          <div><button type="submit" className="small" disabled={busy}>{busy ? "Enviando…" : "Salvar config"}</button></div>
        </form>
      </details>
      <CommandStatus cmd={cmd} error={error} inline />
    </div>
  );
}
