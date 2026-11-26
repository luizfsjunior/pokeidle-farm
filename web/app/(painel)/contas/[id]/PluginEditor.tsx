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
  // Sempre ligado: o worker ignora o `enabled`. Com activeKey o interruptor vale pelo `active` da config;
  // sem ele, não há o que desligar.
  const viaActive = !!info?.alwaysOn && !!info.activeKey;
  const on = viaActive ? config.active !== false : enabled;

  function toggle(next: boolean) {
    if (viaActive) void send(accountId, "plugin.set", { plugin, config: { ...config, active: next } });
    else void send(accountId, "plugin.set", { plugin, enabled: next });
  }

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
        {info?.alwaysOn && !viaActive
          ? <span className="good-text small plugin-toggle">sempre ligado</span>
          : <label className="row plugin-toggle">
              <input type="checkbox" role="switch" checked={on} disabled={busy}
                onChange={(e) => toggle(e.target.checked)} />
              {on ? <span className="good-text small">ligado</span> : <span className="muted small">desligado</span>}
            </label>}
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
