"use client";

import { Hint } from "@/components/Page";

import { useState } from "react";
import { commandSummary } from "@/components/CommandButtons";
import { useCommand } from "@/lib/useCommand";

type Focus = "capture" | "gold_xp_drop" | "rank" | "gems" | "xp";
type PluginRow = { plugin: string; enabled: boolean; config: Record<string, unknown> };

const FOCUS_LABEL: Record<Focus, string> = {
  capture: "Captura",
  gold_xp_drop: "Ouro, XP e drop",
  rank: "Rank semanal",
  gems: "Gemas (pedras)",
  xp: "XP (subir de nível)",
};
// mesma ordem dos padrões do RankConfig (Ultra, Super, Great, Poke)
const BALLS: { id: number; name: string }[] = [
  { id: 4, name: "Ultra" },
  { id: 3, name: "Super" },
  { id: 2, name: "Great" },
  { id: 1, name: "Poke" },
];

/** Foco atual pelas configs gravadas (docs/design/fase-3b-rank-ligado.md, seção 7). */
export function currentFocus(plugins: PluginRow[]): { focus: Focus; label: string } {
  const restock = plugins.find((p) => p.plugin === "restock");
  const rank = plugins.find((p) => p.plugin === "rank");
  const gems = plugins.find((p) => p.plugin === "gems");
  if (gems?.enabled && gems.config.dry_run === false) {
    const f: Focus = gems.config.objective === "xp" ? "xp" : "gems";
    return { focus: f, label: FOCUS_LABEL[f] };
  }
  const restockFocus = (restock?.enabled ? restock.config.focus : undefined) as Focus | undefined;
  const rankOn = rank?.enabled === true;
  const rankDry = rank?.config.dry_run !== false;
  if (restockFocus === "rank") {
    const ok = rankOn && !rankDry;
    return { focus: "rank", label: FOCUS_LABEL.rank + (ok ? "" : " · plugin rank desligado ou em ensaio") };
  }
  // conta sem nada configurado: o padrão do app é gemas (ainda precisa salvar para ligar)
  if (!restock && !gems && !rank) return { focus: "gems", label: `${FOCUS_LABEL.gems} · padrão, ainda não aplicado` };
  const focus: Focus = restockFocus === "capture" ? "capture" : "gold_xp_drop";
  return { focus, label: FOCUS_LABEL[focus] + (rankOn && rankDry ? " · rank em ensaio" : "") };
}

export function FocusCard({ accountId, plugins }: { accountId: string; plugins: PluginRow[] }) {
  const { send, cmd, error, busy } = useCommand();
  const now = currentFocus(plugins);
  const restockCfg = plugins.find((p) => p.plugin === "restock")?.config ?? {};
  const rankCfg = plugins.find((p) => p.plugin === "rank")?.config ?? {};

  const [focus, setFocus] = useState<Focus>(now.focus);
  const [balls, setBalls] = useState<number[]>(
    Array.isArray(rankCfg.rank_balls) ? (rankCfg.rank_balls as number[]) : [4, 3, 2, 1],
  );
  const [rule, setRule] = useState<string>(typeof rankCfg.rank_ball_rule === "string" ? rankCfg.rank_ball_rule : "se_paga");
  const [fallbackFocus, setFallbackFocus] = useState<string>(
    typeof restockCfg.fallback_focus === "string" ? restockCfg.fallback_focus : "gold_xp_drop",
  );
  const [fallbackHunt, setFallbackHunt] = useState<string>(
    typeof rankCfg.fallback_hunt === "string" ? rankCfg.fallback_hunt : "",
  );
  const [formError, setFormError] = useState<string | null>(null);

  function toggleBall(id: number, on: boolean) {
    // mantém a ordem de preferência da lista fixa
    setBalls(BALLS.map((b) => b.id).filter((b) => (b === id ? on : balls.includes(b))));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (focus === "rank" && balls.length === 0) { setFormError("escolha pelo menos uma bola"); return; }
    setFormError(null);
    const params: Record<string, unknown> = { focus };
    if (focus === "rank") {
      params.rank = {
        rank_balls: balls,
        rank_ball_rule: rule,
        fallback_focus: fallbackFocus,
        fallback_hunt: fallbackHunt.trim() || null,
      };
    }
    void send(accountId, "focus.set", params);
  }

  return (
    <form onSubmit={submit} className="card stack">
      <div className="spread">
        <div className="with-hint"><h2 style={{ margin: 0 }}>Foco</h2><Hint>
          <p><strong>XP</strong>: a hunt de mais XP por hora para o nível do pokémon ativo.</p>
          <p><strong>Gemas</strong>: a hunt que mais rende pedras de evolução, sem passar de 10% do que o Mercado vende por semana.</p>
          <p>Nos dois, as bolas ficam desligadas. Salvar grava o <code>restock</code>, o <code>rank</code> e o <code>gems</code> juntos (<code>focus.set</code>).</p>
        </Hint></div>
        <span className="muted small">agora: {now.label}</span>
      </div>
      <div className="row">
        {(Object.keys(FOCUS_LABEL) as Focus[]).map((f) => (
          <label key={f} className="row" style={{ gap: ".35rem" }}>
            <input type="radio" name="focus" checked={focus === f} onChange={() => setFocus(f)} /> {FOCUS_LABEL[f]}
          </label>
        ))}
      </div>
      {focus === "rank" && (
        <fieldset className="stack">
          <legend>Rank semanal</legend>
          <div className="row">
            <span className="small">Bolas:</span>
            {BALLS.map((b) => (
              <label key={b.id} className="row" style={{ gap: ".35rem" }}>
                <input type="checkbox" checked={balls.includes(b.id)} onChange={(e) => toggleBall(b.id, e.target.checked)} /> {b.name}
              </label>
            ))}
          </div>
          <label className="row">
            Regra da bola
            <select value={rule} onChange={(e) => setRule(e.target.value)}>
              <option value="se_paga">a melhor que se paga</option>
              <option value="fixa">a primeira com estoque</option>
            </select>
          </label>
          <label className="row">
            Quando acabar a fila
            <select value={fallbackFocus} onChange={(e) => setFallbackFocus(e.target.value)}>
              <option value="gold_xp_drop">{FOCUS_LABEL.gold_xp_drop}</option>
              <option value="capture">{FOCUS_LABEL.capture}</option>
            </select>
          </label>
          <label className="row">
            Hunt de fallback
            <input value={fallbackHunt} onChange={(e) => setFallbackHunt(e.target.value)} placeholder="vazio = fica onde está" />
          </label>
        </fieldset>
      )}
      {(formError || error) && <p className="error">{formError ?? error}</p>}
      {cmd && <p className={`small ${cmd.status === "failed" ? "error" : "muted"}`}>{commandSummary(cmd)}</p>}
      <div><button type="submit" disabled={busy}>{busy ? "Enviando…" : "Salvar e aplicar"}</button></div>
    </form>
  );
}
