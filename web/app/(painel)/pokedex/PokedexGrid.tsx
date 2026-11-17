"use client";

import { Fragment, useMemo, useState } from "react";
import { CaptureForm, CaptureStatus, type ActiveCapture } from "@/components/Capture";
import { commandSummary } from "@/components/CommandButtons";
import { Matchups, Moves, PvpRange, StatBars, StatRadar } from "@/components/SpeciesFacts";
import { Sprite } from "@/components/Sprite";
import { RARITY_PT, loadGameRules, loadSpeciesInfo } from "@/lib/pokemon";
import { usePanel } from "@/lib/query/hooks";
import { useCommand } from "@/lib/useCommand";
import { dateTime, num } from "@/lib/format";
import type { Atlas } from "@/lib/sprites";

export type DexSpecies = {
  species_id: number;
  name: string | null;
  type1: string | null;
  type2: string | null;
  rarity: string | null;
  hunt_level: number | null;
  evolves_to: number | null;
  evolve_level: number | null;
  stage: string;
  looktype: number | null;
};
export type DexHunt = { slug: string; name: string | null; level: number; species_id: number };
type Entry = { c?: number; k?: number } | number;
type Filter = "todas" | "capturadas" | "vistas" | "faltando";

const FILTERS: [Filter, string][] = [
  ["todas", "Todas"],
  ["capturadas", "Capturadas"],
  ["vistas", "Só vistas"],
  ["faltando", "Faltando"],
];

function caught(e: Entry | undefined): number {
  if (e == null) return 0;
  return typeof e === "number" ? e : e.c ?? 0;
}
function kills(e: Entry | undefined): number | null {
  return e != null && typeof e === "object" && typeof e.k === "number" ? e.k : null;
}

export function PokedexGrid({ species, hunts, dex, atlas, hasProfile, accountId, capture, balls, together, updatedAt }: {
  together?: boolean; // as contas juntas (capturas e abates somados)
  updatedAt?: string | null;
  species: DexSpecies[];
  hunts: DexHunt[];
  dex: Record<string, Entry>;
  atlas: Atlas | null;
  hasProfile: boolean;
  accountId: string | null;
  capture?: ActiveCapture | null;
  balls?: Record<string, number>;
}) {
  const [filter, setFilter] = useState<Filter>("todas");
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const types = useMemo(
    () => [...new Set(species.flatMap((s) => [s.type1, s.type2]).filter((t): t is string => !!t))].sort(),
    [species],
  );
  const huntsBySpecies = useMemo(() => {
    const m = new Map<number, DexHunt[]>();
    for (const h of hunts) m.set(h.species_id, [...(m.get(h.species_id) ?? []), h]);
    return m;
  }, [hunts]);
  const byId = useMemo(() => new Map(species.map((s) => [s.species_id, s])), [species]);

  const counts = useMemo(() => {
    let c = 0, v = 0;
    for (const s of species) {
      const e = dex[String(s.species_id)];
      if (caught(e) > 0) c++;
      else if (e != null) v++;
    }
    return { caught: c, seenOnly: v, missing: species.length - c - v };
  }, [species, dex]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return species.filter((s) => {
      const e = dex[String(s.species_id)];
      const st = caught(e) > 0 ? "capturadas" : e != null ? "vistas" : "faltando";
      if (filter !== "todas" && filter !== st) return false;
      if (type && s.type1 !== type && s.type2 !== type) return false;
      if (q && !(s.name ?? "").toLowerCase().includes(q) && String(s.species_id) !== q) return false;
      return true;
    });
  }, [species, dex, filter, type, query]);

  const sel = selected != null ? byId.get(selected) : undefined;
  const selEntry = sel ? dex[String(sel.species_id)] : undefined;
  const mon = (s: DexSpecies) => ({ id: s.species_id, species_id: s.species_id, name: s.name ?? undefined, looktype: s.looktype ?? undefined });

  return (
    <div className="dex">
      <div className="dex-summary">
        <div className="figure"><span className="figure-value num">{num(counts.caught)}</span><span className="figure-label">capturadas de {num(species.length)}</span></div>
        <div className="figure"><span className="figure-value num">{num(counts.seenOnly)}</span><span className="figure-label">vistas, sem captura</span></div>
        <div className="figure"><span className="figure-value num">{num(counts.missing)}</span><span className="figure-label">faltando</span></div>
        <div className="dex-progress" role="meter" aria-label="Espécies capturadas" aria-valuemin={0} aria-valuemax={species.length} aria-valuenow={counts.caught}>
          <span style={{ width: `${(counts.caught / Math.max(1, species.length)) * 100}%` }} />
        </div>
      </div>
      {!hasProfile && <p className="muted small">Sem perfil da conta ainda: todas aparecem como faltando.</p>}
      {hasProfile && (
        <p className="muted small" style={{ margin: 0 }}>
          {together ? "Todas as contas juntas: capturas e abates somados. " : "A Pokédex é de cada conta, como no jogo. "}
          Atualizada {dateTime(updatedAt)}; a página busca de novo a cada minuto.
        </p>
      )}

      <div className="dex-controls">
        <div className="segmented" role="radiogroup" aria-label="Mostrar">
          {FILTERS.map(([f, label]) => (
            <button key={f} type="button" role="radio" aria-checked={filter === f} className={filter === f ? "on" : undefined} onClick={() => setFilter(f)}>
              {label}
            </button>
          ))}
        </div>
        <input type="search" placeholder="Nome ou número" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Buscar espécie" />
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Tipo">
          <option value="">Todos os tipos</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="muted small">{num(shown.length)} espécies</span>
      </div>

      <div className="dex-body">
        <ul className="dex-grid">
          {shown.map((s) => {
            const e = dex[String(s.species_id)];
            const st = caught(e) > 0 ? "caught" : e != null ? "seen" : "missing";
            return (
              <li key={s.species_id}>
                <button type="button" className={`dex-cell dex-${st} ${selected === s.species_id ? "is-selected" : ""}`}
                  onClick={() => setSelected(s.species_id)} aria-pressed={selected === s.species_id}>
                  <Sprite mon={mon(s)} atlas={atlas} size={48} />
                  <span className="dex-num num">#{s.species_id}</span>
                  <span className="dex-name">{st === "missing" ? "???" : s.name}</span>
                  {st === "caught" && <span className="dex-count num">×{num(caught(e))}</span>}
                </button>
              </li>
            );
          })}
        </ul>

        <aside className={`dex-detail card ${sel ? "is-open" : ""}`} aria-live="polite">
          {sel ? (
            <>
              <button type="button" className="dex-close" onClick={() => setSelected(null)} aria-label="Fechar">×</button>
              <div className="trainer-stage dex-stage"><Sprite mon={mon(sel)} atlas={atlas} size={96} /></div>
              <h2 style={{ marginBottom: ".2rem" }}>{sel.name} <span className="muted num">#{sel.species_id}</span></h2>
              <p className="small" style={{ marginTop: 0 }}>
                {[sel.type1, sel.type2].filter(Boolean).map((t) => <span key={t} className="type-chip">{t}</span>)}
                {sel.rarity && <span className="muted"> {sel.rarity}</span>}
              </p>
              <dl className="dex-facts">
                <dt>Capturas</dt><dd className="num">{num(caught(selEntry))}</dd>
                <dt>Abates</dt><dd className="num">{kills(selEntry) != null ? num(kills(selEntry)) : "—"}</dd>
                {sel.hunt_level != null && <><dt>Nível da hunt</dt><dd className="num">{num(sel.hunt_level)}</dd></>}
                {sel.evolves_to != null && (
                  <>
                    <dt>Evolui para</dt>
                    <dd>
                      <button type="button" className="linklike" onClick={() => setSelected(sel.evolves_to)}>
                        {byId.get(sel.evolves_to)?.name ?? `#${sel.evolves_to}`}
                      </button>
                      {sel.evolve_level != null && <span className="muted"> no nv {sel.evolve_level}</span>}
                    </dd>
                  </>
                )}
                {species.filter((s) => s.evolves_to === sel.species_id).map((s) => (
                  <Fragment key={s.species_id}>
                    <dt>Vem de</dt>
                    <dd><button type="button" className="linklike" onClick={() => setSelected(s.species_id)}>{s.name}</button></dd>
                  </Fragment>
                ))}
              </dl>
              {accountId && (
                capture && capture.species_id === sel.species_id
                  ? <CaptureStatus accountId={accountId} active={capture} />
                  : (
                    <>
                      {capture && <p className="small muted" style={{ margin: 0 }}>Já há uma captura em andamento ({capture.species_name}); começar outra troca o alvo.</p>}
                      <CaptureForm accountId={accountId} speciesId={sel.species_id} speciesName={sel.name ?? `#${sel.species_id}`}
                        hunts={huntsBySpecies.get(sel.species_id) ?? []} balls={balls} />
                    </>
                  )
              )}
              <SpeciesExtra id={sel.species_id} />
              <h3>Onde aparece</h3>
              {(huntsBySpecies.get(sel.species_id) ?? []).length === 0 ? (
                <p className="muted small">Nenhuma hunt tem esta espécie como principal.</p>
              ) : (
                <ul className="small dex-hunts">
                  {huntsBySpecies.get(sel.species_id)!.map((h) => (
                    <li key={h.slug}>
                      {h.name ?? h.slug} <span className="muted">nv {h.level}</span>
                      {accountId && <GoHunt accountId={accountId} slug={h.slug} />}
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="muted small">Escolha uma espécie para ver capturas, evolução e onde ela aparece.</p>
          )}
        </aside>
      </div>
    </div>
  );
}

/** Tipos (fraquezas e forças), stats base, alcance no PvP e golpes da espécie, lidos quando ela é aberta. */
function SpeciesExtra({ id }: { id: number }) {
  const { data: rules } = usePanel(["game-rules"], loadGameRules, { staleTime: 30 * 60_000 });
  const { data: s, isLoading } = usePanel(["species-info", id], (sb) => loadSpeciesInfo(sb, id), { staleTime: 30 * 60_000 });
  if (isLoading) return <p className="muted small">Carregando a ficha…</p>;
  if (!s) return null;
  return (
    <>
      {s.description && <p className="dex-desc">{s.description}</p>}
      <dl className="dex-facts">
        {s.rarity && <><dt>Raridade</dt><dd>{RARITY_PT[s.rarity] ?? s.rarity}</dd></>}
        {s.experience != null && <><dt>XP por derrota</dt><dd className="num">{num(s.experience)}</dd></>}
        {s.price_npc != null && <><dt>O NPC paga</dt><dd className="num">{num(s.price_npc)} de ouro</dd></>}
      </dl>
      <div className="dex-section"><h3>Tipos</h3><Matchups s={s} rules={rules} /></div>
      <div className="dex-section"><h3>Stats base</h3><StatRadar base={s.base} /><details className="stat-table"><summary>Ver os números</summary><StatBars base={s.base} /></details></div>
      <div className="dex-section"><h3>No PvP</h3><PvpRange base={s.base} /></div>
      <div className="dex-section"><h3>Golpes</h3><Moves attacks={s.attacks} /></div>
    </>
  );
}

/** "Ir para esta hunt" por 2 h (comando hunt.select; docs/design/painel-fase-3.md). */
function GoHunt({ accountId, slug }: { accountId: string; slug: string }) {
  const { send, cmd, error, busy } = useCommand();
  return (
    <span className="go-hunt">
      <button type="button" className="ghost small" disabled={busy} onClick={() => void send(accountId, "hunt.select", { slug, hours: 2 })}>
        Ir por 2 h
      </button>
      {(cmd || error) && <span className={`small ${error || cmd?.status === "failed" ? "error" : "muted"}`}> {error ?? (cmd && commandSummary(cmd))}</span>}
    </span>
  );
}
