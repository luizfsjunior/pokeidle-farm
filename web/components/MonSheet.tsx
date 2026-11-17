"use client";

import { useEffect } from "react";
import { Sprite } from "@/components/Sprite";
import { Matchups, Moves, PvpRange, StatBars, TypeChips } from "@/components/SpeciesFacts";
import { dateTime, num } from "@/lib/format";
import {
  BAND_PT, RARITY_PT, bandOf, gradeWithLineage, isLegendary, loadAncestors, loadGameRules, loadSpeciesInfo,
  type Stat,
} from "@/lib/pokemon";
import type { Mon } from "@/lib/profile";
import { usePanel } from "@/lib/query/hooks";
import type { Atlas } from "@/lib/sprites";

const two = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Hora da captura: o jogo manda em ms; aceita também texto ISO. */
function caughtLabel(v: unknown): string | null {
  if (typeof v === "number" && v > 0) return dateTime(new Date(v).toISOString());
  if (typeof v === "string" && v) return dateTime(v);
  return null;
}

/**
 * A ficha de um pokémon da conta, como a do jogo: nota e faixa, potência, qualidade e IV, os stats,
 * os tipos (fraquezas e forças), o alcance no PvP, os golpes e a evolução (docs/design/ficha-pokemon.md).
 */
export function MonSheet({ mon, atlas, looktypes, active, onClose, children }: {
  mon: Mon;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  active?: boolean;
  onClose: () => void;
  children?: React.ReactNode; // ações (tornar ativo, pôr na equipe)
}) {
  const sid = mon.species_id ?? null;
  const { data: rules } = usePanel(["game-rules"], loadGameRules, { staleTime: 30 * 60_000 });
  const sp = usePanel(["species-info", sid], (sb) => loadSpeciesInfo(sb, sid!), { enabled: sid != null, staleTime: 30 * 60_000 });
  const anc = usePanel(["species-ancestors", sid], (sb) => loadAncestors(sb, sid!), { enabled: sid != null, staleTime: 30 * 60_000 });
  const s = sp.data ?? null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ivs = (mon.ivs ?? undefined) as Partial<Record<Stat, number>> | undefined;
  const legendary = isLegendary(s?.rarity ?? null);
  const g = s?.base && ivs && mon.quality != null
    ? gradeWithLineage({ ivs, quality: mon.quality, potency: mon.potency ?? 1, shiny: !!mon.shiny }, s.base, anc.data ?? [], rules?.evoGain ?? null)
    : null;
  const band = g != null && rules ? bandOf(rules.bands, g) : null;
  const xpPct = mon.xp != null && mon.xp_level != null && mon.xp_next != null && mon.xp_next > mon.xp_level
    ? Math.min(1, Math.max(0, (mon.xp - mon.xp_level) / (mon.xp_next - mon.xp_level))) : null;
  const caught = caughtLabel(mon.caught_at);
  const title = mon.nickname || mon.name || s?.name || `#${sid ?? "?"}`;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden />
      <aside className="drawer mon-sheet" role="dialog" aria-modal="true" aria-label={`Ficha de ${title}`}>
        <div className="drawer-head">
          <div className={`drawer-stage sheet-stage ${band ? `band-${band.id}` : ""} ${mon.shiny ? "is-shiny" : ""}`}>
            <Sprite mon={mon} atlas={atlas} looktypes={looktypes} size={88} />
          </div>
          <div>
            <h2>{title}{mon.shiny && <span title="Shiny" aria-label="shiny"> ✨</span>}</h2>
            {mon.nickname && <div className="small muted">{mon.name ?? s?.name}</div>}
            <div className="small">
              <span className="num">Nv {num(mon.level ?? null)}</span>
              {active && <span className="muted"> · ativo</span>}
              {mon.slot != null && !active && <span className="muted"> · na equipe</span>}
            </div>
            {s && <div className="sheet-types"><TypeChips s={s} /></div>}
          </div>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Fechar">×</button>
        </div>

        <div className="drawer-body">
          <div className={`grade-plate ${band ? `band-${band.id}` : ""} ${legendary ? "band-glitch" : ""}`}>
            <span className="grade-label">Nota</span>
            <span className="grade-value num">{legendary ? "Inestimável" : g != null ? two.format(g) : "—"}</span>
            <span className="grade-band">
              {legendary ? "Glitch" : band ? BAND_PT[band.id] ?? band.id : g != null ? "de 0 a 10, dentro da espécie" : "sem IV no perfil ainda"}
            </span>
          </div>

          <div className="sheet-figures">
            <Fig label="Potência" value={mon.potency != null ? `P${mon.potency}` : "—"} />
            <Fig label="Qualidade" value={mon.quality != null ? two.format(mon.quality) : "—"} />
            <Fig label="IV" value={mon.iv_sum != null ? `${mon.iv_sum}/192` : "—"} />
            <Fig label="Poder" value={num(mon.power ?? null, { compact: true })} />
            {mon.max_hp != null && <Fig label="HP" value={`${num(mon.hp ?? null, { compact: true })}/${num(mon.max_hp, { compact: true })}`} />}
            {mon.refine != null && Number(mon.refine) > 0 && <Fig label="Refino" value={`+${num(Number(mon.refine))}`} />}
          </div>

          {xpPct != null && (
            <div>
              <div className="spread small"><span className="muted">XP do nível</span><span className="num">{Math.round(xpPct * 100)}%</span></div>
              <div className="hpbar xpbar"><span style={{ width: `${xpPct * 100}%` }} /></div>
            </div>
          )}

          {children}

          <section>
            <h3>Stats</h3>
            {sp.isLoading ? <p className="muted small">Carregando a espécie…</p> : (
              <StatBars base={s?.base ?? null} ivs={ivs} stats={mon.stats ?? undefined} />
            )}
            {!ivs && <p className="muted small">O IV por stat aparece depois que o worker gravar o perfil de novo (até 2 minutos).</p>}
          </section>

          {s && (
            <>
              <section>
                <h3>Tipos</h3>
                <Matchups s={s} rules={rules} />
              </section>
              <section>
                <h3>No PvP</h3>
                <PvpRange base={s.base} />
              </section>
              <section>
                <h3>Evolução</h3>
                <EvoLine s={s} level={mon.level} />
              </section>
              <section>
                <h3>Golpes</h3>
                <Moves attacks={s.attacks} level={mon.level} />
              </section>
            </>
          )}

          <dl className="dex-facts">
            {s?.rarity && <><dt>Raridade</dt><dd>{RARITY_PT[s.rarity] ?? s.rarity}</dd></>}
            {caught && <><dt>Capturado em</dt><dd>{caught}</dd></>}
            {mon.caught_by && <><dt>Capturado por</dt><dd>{String(mon.caught_by)}</dd></>}
            <dt>ID</dt><dd className="num muted">{mon.id}</dd>
          </dl>
        </div>
      </aside>
    </>
  );
}

function Fig({ label, value }: { label: string; value: string }) {
  return (
    <div className="figure">
      <span className="figure-value num">{value}</span>
      <span className="figure-label">{label}</span>
    </div>
  );
}

export function EvoLine({ s, level }: { s: { evolves_to: number | null; evolves_to_name: string | null; evolve_level: number | null; parents: { species_id: number; name: string | null }[] }; level?: number }) {
  const parts: React.ReactNode[] = [];
  if (s.parents.length) parts.push(<span key="p">Vem de {s.parents.map((p) => p.name ?? `#${p.species_id}`).join(" ou ")}. </span>);
  if (s.evolves_to != null) {
    const need = s.evolve_level;
    parts.push(
      <span key="n">
        Evolui para <b>{s.evolves_to_name ?? `#${s.evolves_to}`}</b>
        {need != null && <> no Nv {num(need)}</>}
        {need != null && level != null && (level >= need ? <span className="good-text"> · nível atingido</span> : <span className="muted"> · faltam {num(need - level)} níveis</span>)}
        .
      </span>,
    );
  } else parts.push(<span key="f" className="muted">Forma final.</span>);
  return <p className="small" style={{ margin: 0 }}>{parts}</p>;
}
