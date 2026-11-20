"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { CaptureForm, CaptureStatus, type ActiveCapture } from "@/components/Capture";
import { Hint } from "@/components/Page";
import { Matchups, Moves, PvpRange, StatBars, StatRadar, TypeChips } from "@/components/SpeciesFacts";
import { Sprite } from "@/components/Sprite";
import { RARITY_PT, captureChance, captureFactor, loadGameRules, loadSpeciesInfo, RULES_VERSION } from "@/lib/pokemon";
import { usePanel } from "@/lib/query/hooks";
import { ago, num } from "@/lib/format";
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
export type DexHunt = { slug: string; name: string | null; level: number; species_id: number; region?: string | null };
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
const keyOf = (s: DexSpecies) => (s.name ?? `#${s.species_id}`).toLowerCase();
/** Capturas e abates somados das formas de um card; nada se a conta não viu nenhuma. */
function groupEntry(dex: Record<string, Entry>, forms: DexSpecies[]): Entry | undefined {
  let c = 0, k = 0, any = false;
  for (const f of forms) {
    const e = dex[String(f.species_id)];
    if (e == null) continue;
    any = true;
    c += caught(e);
    k += kills(e) ?? 0;
  }
  return any ? { c, k } : undefined;
}

export function PokedexGrid({ species, hunts, dex, atlas, hasProfile, accountId, capture, balls, together, updatedAt, level = null }: {
  level?: number | null; // nível do treinador: hunt acima dele fica trancada no jogo
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
  const [region, setRegion] = useState("");
  const [order, setOrder] = useState<"numero" | "hunt">("numero");
  // Pokédex fixa: tudo à mostra (nome, sprite, nível da hunt), sem esconder o que a conta não viu.
  // A escolha fica no navegador.
  const [full, setFullState] = useState(false);
  useEffect(() => {
    try {
      if (localStorage.getItem("dex-modo") === "fixa") { setFullState(true); setOrder("hunt"); }
    } catch { /* sem storage: fica a dinâmica */ }
  }, []);
  const setFull = (on: boolean) => {
    setFullState(on);
    setOrder(on ? "hunt" : "numero");
    try { localStorage.setItem("dex-modo", on ? "fixa" : "dinamica"); } catch { /* ignora */ }
  };
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
  // região da espécie: a da hunt mais baixa em que ela é a principal (as hunts vêm em ordem de nível)
  const regionOf = useMemo(() => {
    const m = new Map<number, string>();
    for (const h of hunts) if (h.region && !m.has(h.species_id)) m.set(h.species_id, h.region);
    return m;
  }, [hunts]);
  // nível da hunt de verdade (game_hunts). O `hunt_level` da espécie é o "Nível ao capturar" do jogo
  // (o nível com que ela nasce ao ser capturada), não o nível de uma hunt.
  const huntLvOf = useMemo(() => {
    const m = new Map<number, number>();
    for (const h of hunts) if (!m.has(h.species_id) || h.level < m.get(h.species_id)!) m.set(h.species_id, h.level);
    return m;
  }, [hunts]);
  const regions = useMemo(() => {
    const first = new Map<string, number>();
    for (const h of hunts) if (h.region && !first.has(h.region)) first.set(h.region, h.level);
    return [...first.entries()].sort((a, b) => a[1] - b[1]).map(([r]) => r);
  }, [hunts]);
  const byId = useMemo(() => new Map(species.map((s) => [s.species_id, s])), [species]);

  // formas do mesmo pokémon com números diferentes (Aron #304 de Kanto e #13304 de Hoenn): um card só
  const formsOf = useMemo(() => {
    const m = new Map<string, DexSpecies[]>();
    for (const s of species) {
      const k = keyOf(s);
      m.set(k, [...(m.get(k) ?? []), s]);
    }
    return m;
  }, [species]);
  // situação de cada card (por nome): capturada se alguma forma foi capturada
  const statusOf = useMemo(() => {
    const m = new Map<string, "capturadas" | "vistas" | "faltando">();
    for (const [k, forms] of formsOf) {
      const e = groupEntry(dex, forms);
      m.set(k, caught(e) > 0 ? "capturadas" : e != null ? "vistas" : "faltando");
    }
    return m;
  }, [formsOf, dex]);
  const counts = useMemo(() => {
    let c = 0, v = 0;
    for (const st of statusOf.values()) { if (st === "capturadas") c++; else if (st === "vistas") v++; }
    return { caught: c, seenOnly: v, total: statusOf.size };
  }, [statusOf]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return species.filter((s) => {
      const st = statusOf.get(keyOf(s)) ?? "faltando";
      if (filter !== "todas" && filter !== st) return false;
      if (type && s.type1 !== type && s.type2 !== type) return false;
      if (region && (regionOf.get(s.species_id) ?? "sem-hunt") !== region) return false;
      if (q && !(s.name ?? "").toLowerCase().includes(q) && String(s.species_id) !== q) return false;
      return true;
    });
  }, [species, statusOf, filter, type, query, region, regionOf]);
  // por nível de hunt: as espécies sem hunt vão para o fim; empate, pelo número
  const sorted = useMemo(() => order === "numero" ? shown : [...shown].sort((a, b) =>
    (huntLvOf.get(a.species_id) ?? Infinity) - (huntLvOf.get(b.species_id) ?? Infinity) || a.species_id - b.species_id), [shown, order, huntLvOf]);

  // um card por nome, na posição da primeira forma que passou nos filtros
  const cards = useMemo(() => {
    const seen = new Set<string>();
    const out: { rep: DexSpecies; forms: DexSpecies[] }[] = [];
    for (const s of sorted) {
      const k = keyOf(s);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({ rep: s, forms: formsOf.get(k) ?? [s] });
    }
    return out;
  }, [sorted, formsOf]);

  const sel = selected != null ? byId.get(selected) : undefined;
  const selEntry = sel ? dex[String(sel.species_id)] : undefined;
  const mon = (s: DexSpecies) => ({ id: s.species_id, species_id: s.species_id, name: s.name ?? undefined, looktype: s.looktype ?? undefined });

  return (
    <div className="dex">
      <div className="dex-summary">
        <p className="dex-line">
          <strong className="num">{num(counts.caught)}</strong> de {num(counts.total)} capturadas
          <span className="muted"> · {num(counts.seenOnly)} só vistas{together ? " · contas somadas" : ""}</span>
          {hasProfile && <span className="muted small" title="O perfil chega a cada ~2 min"> · {ago(updatedAt)}</span>}
        </p>
        <div className="dex-progress" role="meter" aria-label="Pokémons capturados" aria-valuemin={0} aria-valuemax={counts.total} aria-valuenow={counts.caught}>
          <span style={{ width: `${(counts.caught / Math.max(1, counts.total)) * 100}%` }} />
        </div>
      </div>
      {!hasProfile && <p className="muted small">Sem perfil da conta ainda: todos aparecem como faltando.</p>}

      <div className="dex-controls">
        <div className="segmented" role="radiogroup" aria-label="Mostrar">
          {FILTERS.map(([f, label]) => (
            <button key={f} type="button" role="radio" aria-checked={filter === f} className={filter === f ? "on" : undefined} onClick={() => setFilter(f)}>
              {label}
            </button>
          ))}
        </div>
        <input type="search" placeholder="Nome ou número" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Buscar espécie" />
        <details className="dex-more" open={!!(type || region || order !== "numero" || full)}>
          <summary className="ghost small">Filtros{type || region ? " ·" : ""}{type ? ` ${type}` : ""}{region ? ` ${region}` : ""}</summary>
          <div className="dex-more-body">
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Tipo">
          <option value="">Todos os tipos</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Região">
          <option value="">Todas as regiões</option>
          {regions.map((r) => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
          <option value="sem-hunt">Sem hunt</option>
        </select>
        <select value={order} onChange={(e) => setOrder(e.target.value as "numero" | "hunt")} aria-label="Ordenar">
          <option value="numero">Ordem: número</option>
          <option value="hunt">Ordem: nível da hunt</option>
        </select>
        <label className="dex-mode" title="Fixa: mostra todas as espécies com nome, sprite e nível da hunt, mesmo as que a conta ainda não encontrou">
          <input type="checkbox" role="switch" checked={full} onChange={(e) => setFull(e.target.checked)} /> Mostrar tudo
        </label>
          </div>
        </details>
        <span className="muted small">{num(cards.length)} pokémons</span>
      </div>

      <div className="dex-body">
        <ul className="dex-grid">
          {cards.map(({ rep: s, forms }) => {
            const e = groupEntry(dex, forms);
            const st = caught(e) > 0 ? "caught" : e != null ? "seen" : "missing";
            const hide = !full && st === "missing";
            const ids = forms.map((f) => f.species_id);
            const isSel = selected != null && ids.includes(selected);
            const lv = Math.min(...forms.map((f) => huntLvOf.get(f.species_id) ?? Infinity));
            return (
              <li key={s.species_id}>
                <button type="button" className={`dex-cell dex-${st} ${full ? "dex-full" : ""} ${isSel ? "is-selected" : ""}`}
                  onClick={() => setSelected(s.species_id)} aria-pressed={isSel}
                  title={forms.length > 1 ? `${forms.length} formas: ${ids.map((i) => `#${i}`).join(", ")}` : undefined}>
                  <Sprite mon={mon(s)} atlas={atlas} size={48} />
                  <span className="dex-num num">#{s.species_id}</span>
                  <span className="dex-name">{hide ? "???" : s.name}</span>
                  {st === "caught" && <span className="dex-count num">×{num(caught(e))}</span>}
                  {/* uma linha só para o nível da hunt e as formas: em duas, o card ficava mais alto que os vizinhos */}
                  {((order === "hunt" || full) && Number.isFinite(lv)) || forms.length > 1 ? (
                    <span className="dex-meta num">
                      {(order === "hunt" || full) && Number.isFinite(lv) && <span title={`Hunt de nível ${num(lv)}`}>nv {num(lv, { compact: true })}</span>}
                      {forms.length > 1 && <span className="dex-forms">{forms.length} formas</span>}
                    </span>
                  ) : null}
                  {full && st !== "missing" && <span className="dex-mark" aria-label={st === "caught" ? "capturada" : "vista"} title={st === "caught" ? "Capturada" : "Vista"}>{st === "caught" ? "●" : "○"}</span>}
                </button>
              </li>
            );
          })}
        </ul>

        <aside className={`dex-detail card ${sel ? "is-open" : ""}`} aria-live="polite">
          {sel ? (
            <>
              <button type="button" className="dex-close" onClick={() => setSelected(null)} aria-label="Fechar">×</button>
              {(formsOf.get(keyOf(sel)) ?? []).length > 1 && (
                <div className="segmented dex-form-tabs" role="radiogroup" aria-label="Forma">
                  {formsOf.get(keyOf(sel))!.map((f) => {
                    const h = huntsBySpecies.get(f.species_id)?.[0];
                    return (
                      <button key={f.species_id} type="button" role="radio" aria-checked={f.species_id === sel.species_id}
                        className={f.species_id === sel.species_id ? "on" : undefined} onClick={() => setSelected(f.species_id)}>
                        #{f.species_id}<span className="muted small"> {h ? `${h.region ?? ""} nv ${num(h.level)}` : "sem hunt"}</span>
                      </button>
                    );
                  })}
                </div>
              )}
              <div className="trainer-stage dex-stage"><Sprite mon={mon(sel)} atlas={atlas} size={96} /></div>
              <h2 style={{ marginBottom: ".2rem" }}>{sel.name} <span className="muted num">#{sel.species_id}</span></h2>
              <p className="small" style={{ marginTop: 0 }}>
                {/* as mesmas etiquetas de tipo dos Bosses (antes "ROCK GROUND COMMON", em inglês); a raridade fica na ficha abaixo */}
                <TypeChips s={sel} />
              </p>
              <dl className="dex-facts">
                <dt>Capturas</dt><dd className="num">{num(caught(selEntry))}</dd>
                <dt>Abates</dt><dd className="num">{kills(selEntry) != null ? num(kills(selEntry)) : "—"}</dd>
                {huntLvOf.has(sel.species_id) && <><dt>Nível da hunt</dt><dd className="num">{num(huntLvOf.get(sel.species_id)!)}</dd></>}
                {sel.hunt_level != null && <><dt title="O nível com que ela nasce quando você captura">Nível ao capturar</dt><dd className="num">{num(sel.hunt_level)}</dd></>}
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
                      {/* key: sem ela a hunt escolhida da espécie anterior ficava no estado (20/11) */}
                      <CaptureForm key={`${sel.species_id}-${accountId}`} accountId={accountId} speciesId={sel.species_id} speciesName={sel.name ?? `#${sel.species_id}`}
                        hunts={huntsBySpecies.get(sel.species_id) ?? []} balls={balls} level={level} />
                    </>
                  )
              )}
              <SpeciesExtra id={sel.species_id} stage={sel.stage}
                inHunt={(formsOf.get(keyOf(sel)) ?? [sel]).some((f) => (huntsBySpecies.get(f.species_id) ?? []).length > 0)} />
              <h3>Onde aparece</h3>
              {(huntsBySpecies.get(sel.species_id) ?? []).length === 0 ? (
                <OtherForms sel={sel} species={species} huntsBySpecies={huntsBySpecies} accountId={accountId} onPick={setSelected} level={level} />
              ) : (
                <ul className="small dex-hunts">
                  {huntsBySpecies.get(sel.species_id)!.map((h) => (
                    <li key={h.slug}>
                      <span>{h.name ?? h.slug} <span className="muted num">nv {num(h.level)}</span></span>
                      <HuntLock need={h.level} level={level} />
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

/**
 * Espécie sem hunt própria. O jogo tem formas regionais com outro número (ex.: Aron #304 de Kanto
 * e Aron #13304 de Hoenn, que é o da hunt aron_hoenn): mostra as hunts das formas de mesmo nome.
 */
function OtherForms({ sel, species, huntsBySpecies, accountId, onPick, level }: {
  level: number | null;
  sel: DexSpecies;
  species: DexSpecies[];
  huntsBySpecies: Map<number, DexHunt[]>;
  accountId: string | null;
  onPick: (id: number) => void;
}) {
  const name = (sel.name ?? "").toLowerCase();
  const forms = species.filter((s) => s.species_id !== sel.species_id && (s.name ?? "").toLowerCase() === name && (huntsBySpecies.get(s.species_id) ?? []).length);
  return (
    <>
      <p className="muted small" style={{ margin: 0 }}>
        Nenhuma hunt tem a #{sel.species_id} como principal.{forms.length ? " A mesma espécie, em outra forma, aparece em:" : ""}
      </p>
      {forms.map((f) => (
        <div key={f.species_id} className="small" style={{ marginTop: ".4rem" }}>
          <button type="button" className="linklike" onClick={() => onPick(f.species_id)}>{f.name} #{f.species_id}</button>
          <ul className="dex-hunts">
            {huntsBySpecies.get(f.species_id)!.map((h) => (
              <li key={h.slug}>
                <span>{h.name ?? h.slug} <span className="muted num">nv {num(h.level)}{h.region ? ` · ${h.region}` : ""}</span></span>
                <HuntLock need={h.level} level={level} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

/** Tipos (fraquezas e forças), stats base, alcance no PvP e golpes da espécie, lidos quando ela é aberta. */
function SpeciesExtra({ id, stage, inHunt }: { id: number; stage: string; inHunt: boolean }) {
  const { data: rules } = usePanel(["game-rules", RULES_VERSION], loadGameRules, { staleTime: 30 * 60_000 });
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
      {rules?.capture && (
        <div className="dex-section">
          <h3>Captura</h3>
          <CaptureTable rules={rules} factor={captureFactor(rules.capture, stage, inHunt, s.price_npc)} estimated={!inHunt} />
        </div>
      )}
      <div className="dex-section"><h3>Tipos</h3><Matchups s={s} rules={rules} /></div>
      <div className="dex-section"><h3>Stats base</h3><StatRadar base={s.base} /><details className="stat-table"><summary>Ver os números</summary><StatBars base={s.base} /></details></div>
      <div className="dex-section"><h3>No PvP</h3><PvpRange base={s.base} /></div>
      <div className="dex-section"><h3>Golpes</h3><Moves attacks={s.attacks} /></div>
    </>
  );
}

const pctFmt = new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 2 });

/** Chance por bola com o selvagem derrubado, quantos abates por captura e o ouro em bolas; e o shiny. */
function CaptureTable({ rules, factor, estimated }: { rules: NonNullable<Awaited<ReturnType<typeof loadGameRules>>>; factor: number; estimated: boolean }) {
  const cap = rules.capture!;
  return (
    <>
      <table className="moves">
        <thead><tr><th scope="col">Bola</th><th scope="col">Chance</th><th scope="col">Abates por captura</th><th scope="col">Ouro por captura</th></tr></thead>
        <tbody>
          {rules.balls.map((b) => {
            const c = captureChance(cap, b.catchRate, factor);
            return (
              <tr key={b.id}>
                <td>{b.name}</td>
                <td className="num">{pctFmt.format(c)}</td>
                <td className="num">{num(Math.round(1 / c))}</td>
                <td className="num">{b.price != null ? num(Math.round(b.price / c), { compact: true }) : <span className="muted">não se compra</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="small muted" style={{ margin: ".4rem 0 0" }}>
        {rules.shinyChance ? `Shiny: 1 em ${num(Math.round(1 / rules.shinyChance))}. ` : ""}
        <Hint>Uma bola por corpo derrubado. {estimated
          ? "Sem hunt própria, o jogo usa o preço da espécie no fator; aqui vai o preço do NPC, então é uma estimativa."
          : `Fator do degrau da cadeia: ${num(Math.round(factor * 100) / 100)}.`} O shiny não conta bônus (Shiny Secret Lure,
          live e Safari multiplicam).</Hint>
      </p>
    </>
  );
}

/**
 * Só o aviso de hunt trancada: o "Ir por 2 h" saiu daqui (refatoracao-2026-11-20, 4.1). Ir para uma hunt é a hunt
 * manual da aba Agora ou da página Hunts; mirar na espécie é o "Capturar" logo abaixo.
 */
function HuntLock({ need, level }: { need: number; level: number | null }) {
  if (level == null || need <= level) return null;
  return <span className="go-hunt small warn-text" title="O jogo tranca área acima do nível do treinador">trancada: faltam {num(need - level)} níveis</span>;
}
