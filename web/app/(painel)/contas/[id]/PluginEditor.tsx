"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { useCommand } from "@/lib/useCommand";

/** Nome e para que serve cada plugin (a aba Ajustes mostrava só o nome técnico; refatoracao-2026-11-20, 4.3). */
export const PLUGIN_INFO: Record<string, { label: string; hint: string; managed?: string }> = {
  restock: { label: "Reposição", hint: "Compra poções, revives e bolas abaixo do mínimo.", managed: "Modo (aba Agora)" },
  gems: { label: "Plano de hunt (XP/gemas)", hint: "Escolhe a hunt no modo XP.", managed: "Modo (aba Agora)" },
  rank: { label: "Rank semanal", hint: "Fila de espécies do rank, lançando até capturar.", managed: "Modo (aba Agora)" },
  team_train: { label: "Treinar a equipe", hint: "Sobe cada membro até o nível alvo.", managed: "Modo XP (aba Agora)" },
  hunt_hold: { label: "Hunt manual", hint: "Segura a hunt escolhida no painel até o prazo.", managed: "Desvio (aba Agora)" },
  capture_target: { label: "Capturar espécie", hint: "Vai para a hunt da espécie e lança até capturar.", managed: "Pokédex" },
  seller: { label: "Venda no Mercado", hint: "Anuncia as pedras e itens que sobram." },
  market_prices: { label: "Preços do Mercado", hint: "Lê as médias e os anúncios do Mercado de hora em hora." },
  daily: { label: "Prêmios diários", hint: "Resgata o passe e os prêmios do dia." },
  evolve: { label: "Evolução automática", hint: "Evolui o ativo quando tem a pedra." },
};

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
