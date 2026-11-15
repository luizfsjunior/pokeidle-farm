"use client";

import { useState } from "react";
import { commandSummary } from "@/components/CommandButtons";
import { useCommand } from "@/lib/useCommand";

type Focus = "capture" | "gold_xp_drop" | "rank";
type PluginRow = { plugin: string; enabled: boolean; config: Record<string, unknown> };

const FOCUS_LABEL: Record<Focus, string> = {
  capture: "Captura",
  gold_xp_drop: "Ouro, XP e drop",
  rank: "Rank semanal",
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
  const restockFocus = (restock?.enabled ? restock.config.focus : undefined) as Focus | undefined;
  const rankOn = rank?.enabled === true;
  const rankDry = rank?.config.dry_run !== false;
  if (restockFocus === "rank") {
    const ok = rankOn && !rankDry;
    return { focus: "rank", label: FOCUS_LABEL.rank + (ok ? "" : " · plugin rank desligado ou em ensaio") };
  }
  // sem restock ou sem focus na config: o padrão do app
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
        <h2 style={{ margin: 0 }}>Foco</h2>
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
      <p className="muted small" style={{ margin: 0 }}>
        Grava o <code>restock</code> e o <code>rank</code> juntos (comando <code>focus.set</code>). O rank só age de
        verdade com o restock no foco rank; os outros campos continuam nos editores abaixo.
      </p>
    </form>
  );
}
