"use client";

import { num } from "@/lib/format";
import {
  IV_MAX_STAT, RANGE_CUT_3, tierIvStat, RANGE_CUT_4, STAT_LABEL, STATS, TYPE_PT, matchups, pvpRange, rangeLabel,
  type Attack, type GameRules, type SpeciesInfo, type Stat,
} from "@/lib/pokemon";

const mult = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

/** Um tipo como selo colorido (as cores ficam no globals.css, por tipo). */
export function TypeChip({ type, mult: m }: { type: string; mult?: number }) {
  return (
    <span className="type-chip" data-type={type.toUpperCase()}>
      {TYPE_PT[type.toUpperCase()] ?? type}
      {m != null && <b className="type-mult"> ×{mult.format(m)}</b>}
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
      {m.immune.length > 0 && row("Imune a", "Golpes desses tipos não tiram nada", m.immune.map((t) => <TypeChip key={t} type={t} mult={0} />))}
      {row("Forte contra", "Com os golpes do tipo dele, bate ×2 nesses tipos", m.strong.map((t) => <TypeChip key={t} type={t} mult={2} />))}
      {row("Bate fraco em", "Nem o melhor dos tipos dele passa de ×0,5 nesses", m.feeble.map(([t, x]) => <TypeChip key={t} type={t} mult={x} />))}
    </dl>
  );
}

// escala fixa dos stats base: o mesmo comprimento quer dizer o mesmo número em qualquer espécie
// (quase nenhum base passa de 180; quem passa enche a barra)
const BASE_SCALE = 180;

function Meter({ value, max, label, tier }: { value: number | null | undefined; max: number; label: string; tier?: number }) {
  const w = value == null || max <= 0 ? 0 : Math.min(100, (value / max) * 100);
  return (
    <span className={`meter ${tier ? `tier-${tier}` : ""}`} role="img" aria-label={label}>
      <span style={{ width: `${w}%` }} />
    </span>
  );
}

/**
 * Stats de um pokémon: o valor atual (quando o jogo manda), o IV de 1 a 32 e o base da espécie.
 * Cada coluna tem a sua escala e o seu título; sem `stats` nem `ivs`, só o base, em escala fixa.
 */
export function StatBars({ base, ivs, stats, refine }: {
  base: Record<Stat, number> | null;
  ivs?: Partial<Record<Stat, number>>;
  stats?: Partial<Record<string, number>>; // stats de combate que o jogo calcula
  refine?: Partial<Record<string, number>>;
}) {
  if (!base && !ivs && !stats) return null;
  const hasStats = !!stats && STATS.some((k) => stats[k] != null);
  const maxStat = hasStats ? Math.max(...STATS.map((k) => stats![k] ?? 0)) : 0;
  const sum = (f: (k: Stat) => number | undefined) => STATS.reduce((t, k) => t + (f(k) ?? 0), 0);
  const speciesOnly = !hasStats && !ivs;
  return (
    <table className={`statbars ${speciesOnly ? "species-only" : ""}`}>
      <thead>
        <tr>
          <th scope="col"><span className="sr-only">Stat</span></th>
          {hasStats && <th scope="col">Atual</th>}
          {ivs && <th scope="col">IV <span className="muted">de {IV_MAX_STAT}</span></th>}
          <th scope="col">{speciesOnly ? "Base" : <span className="muted">Base</span>}</th>
        </tr>
      </thead>
      <tbody>
        {STATS.map((k) => {
          const b = base?.[k];
          const iv = ivs?.[k];
          const cur = stats?.[k];
          const ref = refine?.[k] ?? 0;
          const tip = [
            STAT_LABEL[k],
            hasStats ? `atual ${num(cur ?? null)}${ref ? ` (refino +${ref})` : ""}` : null,
            ivs ? `IV ${iv ?? "—"} de ${IV_MAX_STAT}` : null,
            `base ${b ?? "—"}`,
          ].filter(Boolean).join(" · ");
          return (
            <tr key={k} title={tip}>
              <th scope="row">{STAT_LABEL[k]}</th>
              {hasStats && (
                <td className="sb-cell">
                  <Meter value={cur} max={maxStat} label={`${STAT_LABEL[k]} ${num(cur ?? null)}`} />
                  <span className="num sb-val">{num(cur ?? null)}</span>
                  {ref > 0 && <span className="small muted"> +{ref}</span>}
                </td>
              )}
              {ivs && (
                <td className="sb-cell">
                  <Meter value={iv} max={IV_MAX_STAT} label={`IV ${iv ?? "—"} de ${IV_MAX_STAT}`} tier={iv != null ? tierIvStat(iv) : undefined} />
                  <span className="num sb-val">{iv ?? "—"}</span>
                  {iv === IV_MAX_STAT && <span className="sb-perfect" title="IV máximo"> ★</span>}
                </td>
              )}
              {speciesOnly ? (
                <td className="sb-cell">
                  <Meter value={b} max={BASE_SCALE} label={`${STAT_LABEL[k]} base ${b ?? "—"}`} />
                  <span className="num sb-val">{b ?? "—"}</span>
                </td>
              ) : (
                <td className="num muted">{b ?? "—"}</td>
              )}
            </tr>
          );
        })}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row">Total</th>
          {hasStats && <td className="num sb-total">{num(sum((k) => stats![k]))}</td>}
          {ivs && <td className="num sb-total">{sum((k) => ivs[k])} <span className="muted">de {IV_MAX_STAT * 6}</span></td>}
          <td className={`num ${speciesOnly ? "sb-total" : "muted"}`}>{base ? sum((k) => base[k]) : "—"}</td>
        </tr>
      </tfoot>
    </table>
  );
}

// a ordem do radar do jogo (ORDEM_RADAR no app.js): HP no topo, sentido horário
const RADAR_ORDER: Stat[] = ["hp", "atk", "def", "speed", "spDef", "spAtk"];
const RADAR_SHORT: Record<Stat, string> = { hp: "HP", atk: "Atq", def: "Def", speed: "Vel", spDef: "Sp.Def", spAtk: "Sp.Atk" };
const R = 84;
const pt = (i: number, v: number): [number, number] => {
  const a = ((-90 + i * 60) * Math.PI) / 180;
  return [Math.cos(a) * R * v, Math.sin(a) * R * v];
};
const poly = (f: (k: Stat) => number) => RADAR_ORDER.map((k, i) => pt(i, f(k)).map((n) => n.toFixed(1)).join(",")).join(" ");
const clamp = (v: number) => Math.max(0.04, Math.min(1, v));

/**
 * O hexágono dos stats, como na ficha do jogo. Pokémon seu: os stats atuais (em relação ao maior
 * deles) e o IV (de 32) sobrepostos. Espécie: o base (de 200). Os números ficam nas pontas.
 */
export function StatRadar({ base, ivs, stats }: {
  base: Record<Stat, number> | null;
  ivs?: Partial<Record<Stat, number>>;
  stats?: Partial<Record<string, number>>;
}) {
  const hasStats = !!stats && STATS.some((k) => stats[k] != null);
  const maxStat = hasStats ? Math.max(1, ...STATS.map((k) => stats![k] ?? 0)) : 1;
  const series: { key: string; label: string; v: (k: Stat) => number }[] = [];
  if (hasStats) series.push({ key: "stats", label: "Stats atuais", v: (k) => (stats![k] ?? 0) / maxStat });
  if (ivs) series.push({ key: "iv", label: `IV (de ${IV_MAX_STAT})`, v: (k) => (ivs[k] ?? 0) / IV_MAX_STAT });
  if (!series.length && base) series.push({ key: "base", label: "Base", v: (k) => base[k] / 200 });
  if (!series.length) return null;
  const tip = (k: Stat) => [STAT_LABEL[k], hasStats ? `atual ${num(stats![k] ?? null)}` : null, ivs ? `IV ${ivs[k] ?? "—"} de ${IV_MAX_STAT}` : null, base ? `base ${base[k]}` : null].filter(Boolean).join(" · ");
  return (
    <figure className="radar">
      <svg viewBox="-160 -130 320 258" role="img" aria-label={`Stats: ${STATS.map(tip).join("; ")}`}>
        {[0.25, 0.5, 0.75, 1].map((v) => <polygon key={v} className="radar-ring" points={poly(() => v)} />)}
        {RADAR_ORDER.map((k, i) => { const [x, y] = pt(i, 1); return <line key={k} className="radar-axis" x1={0} y1={0} x2={x} y2={y} />; })}
        {series.map((s) => <polygon key={s.key} className={`radar-shape ${s.key}`} points={poly((k) => clamp(s.v(k)))} />)}
        {series.map((s) => RADAR_ORDER.map((k, i) => {
          const [x, y] = pt(i, clamp(s.v(k)));
          return <circle key={`${s.key}-${k}`} className={`radar-dot ${s.key}`} cx={x} cy={y} r={3.5} />;
        }))}
        {RADAR_ORDER.map((k, i) => {
          const [x, y] = pt(i, 1.27);
          const main = hasStats ? num(stats![k] ?? null) : ivs ? String(ivs[k] ?? "—") : String(base?.[k] ?? "—");
          const sub = hasStats && ivs ? `IV ${ivs[k] ?? "—"}` : !hasStats && ivs && base ? `base ${base[k]}` : null;
          const anchor = Math.abs(x) < 1 ? "middle" : x > 0 ? "start" : "end";
          return (
            <g key={k} className="radar-label">
              <title>{tip(k)}</title>
              {/* área de toque maior que o texto, para o balão no celular */}
              <circle cx={x} cy={y} r={18} className="radar-hit" />
              <text x={x} y={y - (sub ? 6 : 0)} textAnchor={anchor} dominantBaseline="middle">
                <tspan className="radar-name">{RADAR_SHORT[k]} </tspan><tspan className="radar-val">{main}</tspan>
              </text>
              {sub && <text x={x} y={y + 8} textAnchor={anchor} dominantBaseline="middle" className="radar-sub">{sub}{ivs?.[k] === IV_MAX_STAT ? " ★" : ""}</text>}
            </g>
          );
        })}
      </svg>
      {series.length > 1 && (
        <figcaption className="radar-legend">
          {series.map((s) => <span key={s.key}><i className={`radar-key ${s.key}`} aria-hidden />{s.label}</span>)}
        </figcaption>
      )}
    </figure>
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
