"use client";

import { useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { BALL_NAMES } from "@/lib/sprites";
import { useCommand } from "@/lib/useCommand";

/**
 * Modo da conta (docs/design/refatoracao-2026-11-20.md, seção 3): o que ela faz sozinha. "Bola em tudo" e
 * "treinar a equipe" são opções do modo, não focos separados (antes "Captura" era um foco e confundia com o
 * "Capturar esta espécie" da Pokédex, que é um desvio).
 */
export type Mode = "xp" | "gold_xp_drop" | "rank" | "gems" | "outland";
type PluginRow = { plugin: string; enabled: boolean; config: Record<string, unknown> };

export const MODE_LABEL: Record<Mode, string> = {
  xp: "XP (subir de nível)",
  gold_xp_drop: "Ouro e drop",
  rank: "Rank semanal",
  gems: "Gemas (pedras)",
  outland: "Outland (drops raros)",
};
const MODE_HINT: Record<Mode, string> = {
  xp: "Vai para a hunt de mais XP por hora que o pokémon aguenta.",
  gold_xp_drop: "Fica na hunt em que está (ou na que você escolher) e só cuida de poções e bolas.",
  rank: "Percorre a fila de espécies do rank semanal, lançando até capturar.",
  gems: "Hunt que mais rende pedras. Pedras vendem a 2 gemas: prefira outro modo.",
  outland: "Hunt da Outland onde o pokémon abate mais rápido (fragmentos e Boss Token). Antes do 150, sobe de nível como no XP.",
};
const OFFERED: Mode[] = ["xp", "outland", "gold_xp_drop", "rank"];
// ordem de preferência dos padrões do RankConfig (Ultra, Super, Great, Poke); os nomes vêm de lib/sprites
const BALLS = [4, 3, 2, 1].map((id) => ({ id, name: BALL_NAMES[String(id)] ?? `Bola ${id}` }));

export type ModeState = {
  mode: Mode;
  catchAll: boolean;
  train: { on: boolean; target: number };
  label: string;
  warn: string | null;
};

const cfgOf = (plugins: PluginRow[], name: string) => plugins.find((p) => p.plugin === name);

/** Modo atual pelas configs gravadas. */
export function currentMode(plugins: PluginRow[]): ModeState {
  const restock = cfgOf(plugins, "restock");
  const rank = cfgOf(plugins, "rank");
  const gems = cfgOf(plugins, "gems");
  const tt = cfgOf(plugins, "team_train");
  const restockFocus = restock?.enabled ? restock.config.focus : undefined;
  const train = { on: tt?.enabled === true, target: typeof tt?.config.target_level === "number" ? tt.config.target_level : 300 };
  let mode: Mode = "gold_xp_drop";
  let warn: string | null = null;
  if (gems?.enabled && gems.config.dry_run === false) {
    mode = gems.config.objective === "xp" ? "xp" : gems.config.objective === "outland" ? "outland" : "gems";
  }
  else if (restockFocus === "rank") {
    mode = "rank";
    if (!(rank?.enabled && rank.config.dry_run === false)) warn = "o plugin rank está desligado ou em ensaio";
  }
  if (!restock && !gems && !rank) warn = "nada configurado ainda: salve um modo";
  const catchAll = mode !== "rank" && restockFocus === "capture";
  const parts = [MODE_LABEL[mode]];
  if (mode === "xp" && train.on) parts.push(`treinando a equipe até o ${train.target}`);
  if (catchAll) parts.push("bola em tudo");
  if (mode !== "xp" && train.on) warn = "treino ligado fora do modo XP: salve o modo de novo";
  return { mode, catchAll, train, label: parts.join(" · "), warn };
}

/** Trocar o modo e as opções (comando focus.set, que grava restock, rank, gems e team_train juntos). */
export function ModeForm({ accountId, plugins, teamSize }: { accountId: string; plugins: PluginRow[]; teamSize: number }) {
  const { send, cmd, error, busy } = useCommand();
  const now = currentMode(plugins);
  const restockCfg = cfgOf(plugins, "restock")?.config ?? {};
  const rankCfg = cfgOf(plugins, "rank")?.config ?? {};

  const [mode, setMode] = useState<Mode>(now.mode === "gems" ? "xp" : now.mode);
  const [catchAll, setCatchAll] = useState(now.catchAll);
  const [train, setTrain] = useState(now.train.on);
  const [targetText, setTargetText] = useState(String(now.train.target));
  const [balls, setBalls] = useState<number[]>(Array.isArray(rankCfg.rank_balls) ? (rankCfg.rank_balls as number[]) : [4, 3, 2, 1]);
  const [rule, setRule] = useState<string>(typeof rankCfg.rank_ball_rule === "string" ? rankCfg.rank_ball_rule : "se_paga");
  const [fallbackCatch, setFallbackCatch] = useState(restockCfg.fallback_focus === "capture");
  const [fallbackHunt, setFallbackHunt] = useState<string>(typeof rankCfg.fallback_hunt === "string" ? rankCfg.fallback_hunt : "");
  const [formError, setFormError] = useState<string | null>(null);

  const parsed = Math.round(Number(targetText));
  const target = targetText.trim() && Number.isFinite(parsed) ? Math.min(100_000, Math.max(2, parsed)) : now.train.target;

  function toggleBall(id: number, on: boolean) {
    setBalls(BALLS.map((b) => b.id).filter((b) => (b === id ? on : balls.includes(b))));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (mode === "rank" && balls.length === 0) { setFormError("escolha pelo menos uma bola"); return; }
    setFormError(null);
    const params: Record<string, unknown> = { focus: mode };
    if (mode !== "rank") params.catch_all = catchAll;
    if (mode === "xp") params.train = { enabled: train, target_level: target };
    if (mode === "rank") {
      params.rank = {
        rank_balls: balls,
        rank_ball_rule: rule,
        fallback_focus: fallbackCatch ? "capture" : "gold_xp_drop",
        fallback_hunt: fallbackHunt.trim() || null,
      };
    }
    void send(accountId, "focus.set", params);
  }

  return (
    <form onSubmit={submit} className="stack mode-form">
      {now.mode === "gems" && (
        <p className="small warn-text" style={{ margin: 0 }}>O modo por pedras rende quase nada (vendem a 2 gemas). Salve outro.</p>
      )}
      <div className="mode-options" role="radiogroup" aria-label="Modo">
        {OFFERED.map((m) => (
          <label key={m} className={`mode-option ${mode === m ? "is-on" : ""}`}>
            <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
            <span><strong>{MODE_LABEL[m]}</strong><span className="small muted">{MODE_HINT[m]}</span></span>
          </label>
        ))}
      </div>

      {mode === "xp" && (
        <fieldset className="stack">
          <legend>Treinar a equipe</legend>
          <label className="row" style={{ gap: ".4rem" }}>
            <input type="checkbox" checked={train} onChange={(e) => setTrain(e.target.checked)} disabled={teamSize === 0} />
            Subir cada membro até o nível
            <input type="number" inputMode="numeric" min={2} max={100000} value={targetText} style={{ width: "6rem" }}
              onChange={(e) => setTargetText(e.target.value)} onBlur={() => setTargetText(String(target))} disabled={!train} />
          </label>
          <p className="small muted" style={{ margin: 0 }}>
            Treina o mais fraco por vez. A hunt é escolhida para ele, e a troca do ativo só acontece quando a conta já está numa
            hunt que ele aguenta (até 10 níveis acima dele). Se ele morrer em loop, a vigia volta o mais forte.
          </p>
        </fieldset>
      )}

      {mode !== "rank" && (
        <label className="row" style={{ gap: ".4rem" }}>
          <input type="checkbox" checked={catchAll} onChange={(e) => setCatchAll(e.target.checked)} />
          Jogar bola em todo selvagem <span className="small muted">(a melhor bola que se paga pelo ouro do abate)</span>
        </label>
      )}

      {mode === "rank" && (
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
          <label className="row" style={{ gap: ".4rem" }}>
            <input type="checkbox" checked={fallbackCatch} onChange={(e) => setFallbackCatch(e.target.checked)} />
            Quando a fila acabar, jogar bola em todo selvagem
          </label>
          <label className="row">
            Hunt quando a fila acabar
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
