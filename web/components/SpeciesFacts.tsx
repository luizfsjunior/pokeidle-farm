"use client";

import { num } from "@/lib/format";
import {
  IV_MAX_STAT, RANGE_CUT_3, RANGE_CUT_4, STAT_LABEL, STATS, TYPE_PT, matchups, pvpRange, rangeLabel,
  type Attack, type GameRules, type SpeciesInfo, type Stat,
} from "@/lib/pokemon";

const mult = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

/** Um tipo como selo colorido (as cores ficam no globals.css, por tipo). */
export function TypeChip({ type, mult: m }: { type: string; mult?: number }) {
  return (
    <span className="type-chip" data-type={type.toUpperCase()}>
      {TYPE_PT[type.toUpperCase()] ?? type}
      {m != null && m !== 2 && m !== 0.5 && <b className="type-mult"> ×{mult.format(m)}</b>}
    </span>
  );
}

export function TypeChips({ s }: { s: Pick<SpeciesInfo, "type1" | "type2"> }) {
  return <>{[s.type1, s.type2].filter((t): t is string => !!t).map((t) => <TypeChip key={t} type={t} />)}</>;
}

/** Fraquezas, resistências e onde os tipos dele batem forte (pela tabela de tipos do jogo). */
export function Matchups({ s, rules }: { s: Pick<SpeciesInfo, "type1" | "type2">; rules: GameRules | undefined }) {
  const m = rules ? matchups(rules.types, s.type1, s.type2) : null;
  if (!m) return <p className="muted small">A tabela de tipos ainda não foi lida do jogo.</p>;
  const row = (label: string, hint: string, chips: React.ReactNode[], empty = "nenhum") => (
    <div className="mu-row">
      <dt title={hint}>{label}</dt>
      <dd>{chips.length ? chips : <span className="muted small">{empty}</span>}</dd>
    </div>
  );
  return (
    <dl className="matchups">
      {row("Fraco contra", "Golpes desses tipos tiram ×2 (ou ×4) dele", m.weak.map(([t, x]) => <TypeChip key={t} type={t} mult={x} />))}
      {row("Resiste a", "Golpes desses tipos tiram ×0,5 (ou ×0,25)", m.resist.map(([t, x]) => <TypeChip key={t} type={t} mult={x} />))}
      {m.immune.length > 0 && row("Imune a", "Golpes desses tipos não tiram nada", m.immune.map((t) => <TypeChip key={t} type={t} />))}
      {row("Forte contra", "Com os golpes do tipo dele, bate ×2 nesses tipos", m.strong.map((t) => <TypeChip key={t} type={t} />))}
      {row("Bate fraco em", "Nem o melhor dos tipos dele passa de ×0,5 nesses", m.feeble.map(([t, x]) => <TypeChip key={t} type={t} mult={x} />))}
    </dl>
  );
}

/** Stats base da espécie e, para um pokémon seu, o IV de cada stat (1 a 32). */
export function StatBars({ base, ivs, stats }: {
  base: Record<Stat, number> | null;
  ivs?: Partial<Record<Stat, number>>;
  stats?: Partial<Record<string, number>>; // os stats de combate, quando o jogo manda
}) {
  if (!base && !ivs) return null;
  const maxBase = 160;
  return (
    <table className="statbars">
      <thead>
        <tr><th scope="col">Stat</th><th scope="col">Base</th>{ivs && <th scope="col">IV</th>}{stats && <th scope="col">Atual</th>}</tr>
      </thead>
      <tbody>
        {STATS.map((k) => {
          const b = base?.[k];
          const iv = ivs?.[k];
          return (
            <tr key={k}>
              <th scope="row">{STAT_LABEL[k]}</th>
              <td>
                <span className="statbar"><span style={{ width: `${Math.min(100, ((b ?? 0) / maxBase) * 100)}%` }} /></span>
                <span className="num">{b ?? "—"}</span>
              </td>
              {ivs && (
                <td>
                  <span className={`statbar iv ${iv != null && iv >= 28 ? "hi" : iv != null && iv <= 8 ? "lo" : ""}`}>
                    <span style={{ width: `${((iv ?? 0) / IV_MAX_STAT) * 100}%` }} />
                  </span>
                  <span className="num">{iv ?? "—"}</span>
                </td>
              )}
              {stats && <td className="num">{num(stats[k] ?? null)}</td>}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Alcance no PvP ranqueado (tabuleiro): pelos stats base, não muda com IV, nível ou qualidade. */
export function PvpRange({ base }: { base: Record<Stat, number> | null }) {
  const r = pvpRange(base);
  if (!r || !base) return null;
  return (
    <div className="pvp-range">
      <span className={`range-badge ${r.range > 1 ? "far" : "near"}`}>{rangeLabel(r.range)}</span>
      <div className="small">
        <b>{r.range > 1 ? `Ataca a ${r.range} casas` : "Corpo a corpo"}</b> no tabuleiro do PvP.
        <span className="muted"> Folga = Sp. Atk {base.spAtk} − maior entre Ataque {base.atk} e HP {base.hp} = {r.slack}
          {" "}(≤ 0 corpo a corpo; 1–{RANGE_CUT_3 - 1} → 2; {RANGE_CUT_3}–{RANGE_CUT_4 - 1} → 3; {RANGE_CUT_4}+ → 4). Evoluir muda; IV e nível não.</span>
      </div>
    </div>
  );
}

const cat = (c?: string) => (c === "PHYSICAL" ? "Físico" : c === "SPECIAL" ? "Especial" : c ?? "");

/** Golpes da espécie: os aprendidos até o nível marcados; os de TM à parte. */
export function Moves({ attacks, level }: { attacks: Attack[]; level?: number }) {
  if (attacks.length === 0) return <p className="muted small">Sem golpes no catálogo.</p>;
  const learn = attacks.filter((a) => !a.tm).sort((a, b) => (a.learnLevel ?? 0) - (b.learnLevel ?? 0) || b.power - a.power);
  const tms = attacks.filter((a) => a.tm);
  return (
    <table className="moves">
      <thead><tr><th scope="col">Golpe</th><th scope="col">Tipo</th><th scope="col">Power</th><th scope="col">Recarga</th><th scope="col">Nv</th></tr></thead>
      <tbody>
        {[...learn, ...tms].map((a) => {
          const has = !a.tm && level != null && (a.learnLevel ?? 0) <= level;
          return (
            <tr key={`${a.name}-${a.tm ?? a.learnLevel}`} className={level != null && !has && !a.tm ? "muted" : undefined}>
              <td>{a.name}{a.tm && <span className="muted small"> TM</span>}<span className="muted small"> {cat(a.category)}</span></td>
              <td><TypeChip type={a.type} /></td>
              <td className="num">{num(a.power)}</td>
              <td className="num">{a.cooldownMs != null ? `${num(a.cooldownMs / 1000)} s` : "—"}</td>
              <td className="num">{a.tm ? "TM" : num(a.learnLevel ?? 1)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
