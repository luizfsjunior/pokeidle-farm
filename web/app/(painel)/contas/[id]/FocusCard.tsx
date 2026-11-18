"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { BALL_NAMES } from "@/lib/sprites";
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
// Gemas por pedra saiu da lista (17/11): as pedras vendem a 2 gemas com filas de semanas
// (docs/design/outland-potencial.md). Só aparece para a conta que ainda está nele.
const OFFERED: Focus[] = ["xp", "gold_xp_drop", "capture", "rank"];
// ordem de preferência dos padrões do RankConfig (Ultra, Super, Great, Poke); os nomes vêm de lib/sprites
const BALLS = [4, 3, 2, 1].map((id) => ({ id, name: BALL_NAMES[String(id)] ?? `Bola ${id}` }));

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
  // conta sem nada configurado: o padrão sugerido é XP (ainda precisa salvar para ligar)
  if (!restock && !gems && !rank) return { focus: "xp", label: `${FOCUS_LABEL.xp} · sugerido, ainda não aplicado` };
  const focus: Focus = restockFocus === "capture" ? "capture" : "gold_xp_drop";
  return { focus, label: FOCUS_LABEL[focus] + (rankOn && rankDry ? " · rank em ensaio" : "") };
}

/** Trocar o foco (comando focus.set, grava restock, rank e gems juntos). Fica dentro do card "Fazendo agora". */
export function FocusForm({ accountId, plugins }: { accountId: string; plugins: PluginRow[] }) {
  const { send, cmd, error, busy } = useCommand();
  const now = currentFocus(plugins);
  const restockCfg = plugins.find((p) => p.plugin === "restock")?.config ?? {};
  const rankCfg = plugins.find((p) => p.plugin === "rank")?.config ?? {};

  const [focus, setFocus] = useState<Focus>(now.focus === "gems" ? "xp" : now.focus);
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
    <form onSubmit={submit} className="stack">
      {now.focus === "gems" && (
        <p className="small warn-text" style={{ margin: 0 }}>
          O foco por pedras rende quase nada (vendem a 2 gemas). Salve outro: o sugerido é XP, até a Outland.
        </p>
      )}
      <div className="row">
        {OFFERED.map((f) => (
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
      {formError && <p className="error small" style={{ margin: 0 }}>{formError}</p>}
      <CommandStatus cmd={cmd} error={error} />
      <div><button type="submit" disabled={busy}>{busy ? "Enviando…" : "Salvar e aplicar"}</button></div>
    </form>
  );
}
