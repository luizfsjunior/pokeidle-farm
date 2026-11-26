"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { useCommand } from "@/lib/useCommand";

/** Avisos no Discord (plugin notifier, épico A): um interruptor por tipo, o corte da captura rara, os drops e o
 * aviso de teste. A config vai para strategy_configs pelo plugin.set; o webhook fica só no .env do worker. */

const TYPES: { key: string; label: string; hint: string }[] = [
  { key: "shiny_seen", label: "Shiny visto", hint: "Um por corpo; avisa também quando faltou bola." },
  { key: "shiny_captured", label: "Shiny capturado", hint: "Sempre." },
  { key: "rare_capture", label: "Captura rara", hint: "Potência ou nota no corte abaixo." },
  { key: "rare_drop", label: "Drop raro", hint: "Itens da lista abaixo." },
  { key: "account_down", label: "Conta caiu", hint: "Desconectada, sessão encerrada ou sem abates; e a volta." },
  { key: "rank", label: "Top Catch", hint: "Quando muda de faixa (top 1, 3, 10, 50, 100)." },
  { key: "level", label: "Nível", hint: "Marcos do treinador (100, 150, 200...)." },
];

// o padrão do worker (NotifierConfig), para o card mostrar o que vale sem config gravada
const DEFAULTS = { min_potency: 4, top_pct: 5, down_after_min: 10, drops: ["fragment", "boss token", "shiny stone"] };

export function NotifierEditor({ accountId, config }: { accountId: string; config: Record<string, unknown> }) {
  const save = useCommand();
  const test = useCommand();
  const on = config.active !== false;
  const num = (k: keyof typeof DEFAULTS) => String(typeof config[k] === "number" ? config[k] : DEFAULTS[k]);
  const [types, setTypes] = useState(() => Object.fromEntries(TYPES.map((t) => [t.key, config[t.key] !== false])));
  const [potency, setPotency] = useState(num("min_potency"));
  const [topPct, setTopPct] = useState(num("top_pct"));
  const [downMin, setDownMin] = useState(num("down_after_min"));
  const [drops, setDrops] = useState(
    (Array.isArray(config.drops) ? (config.drops as string[]) : DEFAULTS.drops).join(", "),
  );

  function toggle(next: boolean) {
    void save.send(accountId, "plugin.set", { plugin: "notifier", config: { ...config, active: next } });
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const next: Record<string, unknown> = {
      ...config,
      ...types,
      min_potency: Math.min(5, Math.max(1, Math.round(Number(potency) || DEFAULTS.min_potency))),
      top_pct: Math.min(50, Math.max(0, Number(topPct) || 0)),
      down_after_min: Math.max(1, Number(downMin) || DEFAULTS.down_after_min),
      drops: drops.split(",").map((s) => s.trim()).filter(Boolean),
    };
    void save.send(accountId, "plugin.set", { plugin: "notifier", config: next });
  }

  const busy = save.busy || test.busy;
  return (
    <div className="plugin-row">
      <div className="plugin-head">
        <span>
          <strong>Avisos no Discord</strong> <code className="small muted">notifier</code>
          <span className="small muted plugin-hint">
            Manda shiny, captura rara, drop raro, queda, rank e nível para o webhook do .env do worker
            (DISCORD_WEBHOOK_URL). No máximo 10 por minuto somando as contas; o resto vira um resumo.
          </span>
        </span>
        <label className="row plugin-toggle">
          <input type="checkbox" role="switch" checked={on} disabled={busy} onChange={(e) => toggle(e.target.checked)} />
          {on ? <span className="good-text small">ligado</span> : <span className="muted small">desligado</span>}
        </label>
      </div>
      <form onSubmit={submit} className="stack">
        <fieldset className="stack" disabled={busy} style={{ border: 0, padding: 0, margin: 0, gap: 4 }}>
          {TYPES.map((t) => (
            <label key={t.key} className="row small">
              <input type="checkbox" checked={types[t.key]}
                onChange={(e) => setTypes((s) => ({ ...s, [t.key]: e.target.checked }))} />
              <span><strong>{t.label}</strong> <span className="muted">{t.hint}</span></span>
            </label>
          ))}
        </fieldset>
        <div className="row small" style={{ flexWrap: "wrap", gap: 12 }}>
          <label>Potência mínima{" "}
            <input type="number" min={1} max={5} value={potency} onChange={(e) => setPotency(e.target.value)} style={{ width: 56 }} />
          </label>
          <label title="0 desliga o corte pela nota">Ou nota no top{" "}
            <input type="number" min={0} max={50} step={0.5} value={topPct} onChange={(e) => setTopPct(e.target.value)} style={{ width: 64 }} />
            % da espécie
          </label>
          <label>Queda depois de{" "}
            <input type="number" min={1} value={downMin} onChange={(e) => setDownMin(e.target.value)} style={{ width: 64 }} /> min
          </label>
        </div>
        <label className="stack small">
          Drops raros (o nome do item contém; separe por vírgula)
          <input type="text" value={drops} onChange={(e) => setDrops(e.target.value)} />
        </label>
        <div className="row">
          <button type="submit" className="small" disabled={busy}>{save.busy ? "Enviando…" : "Salvar avisos"}</button>
          <button type="button" className="small" disabled={busy} onClick={() => void test.send(accountId, "notify.test")}>
            {test.busy ? "Mandando…" : "Mandar aviso de teste"}
          </button>
        </div>
      </form>
      <CommandStatus cmd={save.cmd} error={save.error} inline />
      <CommandStatus cmd={test.cmd} error={test.error} inline />
    </div>
  );
}
