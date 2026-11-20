"use client";

import { useEffect, useMemo, useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { MonSheet } from "@/components/MonSheet";
import { Panel } from "@/components/Page";
import { Sprite } from "@/components/Sprite";
import { loadTypes } from "@/lib/bosses";
import {
  loadCollection, placeOf, PLACE_PT, SORT_PT, sortCollection,
  type CollectionMon, type Place, type SortKey,
} from "@/lib/collection";
import { num } from "@/lib/format";
import { TYPE_PT, TYPES, tierIvSum, tierPotency, tierQuality } from "@/lib/pokemon";
import type { Profile } from "@/lib/profile";
import { usePanel } from "@/lib/query/hooks";
import type { Atlas } from "@/lib/sprites";
import { useCommand } from "@/lib/useCommand";
import { MonTable } from "./MonTable";
import { SellDepot } from "./SellDepot";
import { TeamBuilder, TEAM_SLOTS, toggleInDraft, useDraft, type Draft } from "./TeamBuilder";
import { MonActions } from "./TeamControls";

const PAGE = 60;
type View = "grade" | "tabela";
const VIEW_KEY = "pokemons-view";
const BATCH_MAX = 100; // o comando aceita até 100 por vez

function readView(): View {
  try { return localStorage.getItem(VIEW_KEY) === "tabela" ? "tabela" : "grade"; } catch { return "grade"; }
}

/**
 * Os pokémons da conta (docs/design/refatoracao-2026-11-20.md, 4.2): uma lista só (antes a equipe aparecia em
 * três lugares e "Coleção" tinha três sentidos), em grade ou numa tabela de comparação. Clicar abre a ficha,
 * também durante a montagem da equipe (antes clicar já punha na vaga e não dava para ver os stats).
 */
export function Collection({ accountId, profile, atlas, looktypes, training = false }: {
  training?: boolean;
  accountId: string;
  profile: Profile;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
}) {
  const q = usePanel(["collection", accountId], (sb) => loadCollection(sb, accountId), { staleTime: 30_000 });
  const all = useMemo(() => q.data ?? [], [q.data]);
  const speciesIds = useMemo(
    () => [...new Set(all.map((m) => m.species_id).filter((x): x is number => x != null))].sort((a, b) => a - b),
    [all],
  );
  const types = usePanel(["mon-types", speciesIds.join(",")], (sb) => loadTypes(sb, speciesIds),
    { enabled: speciesIds.length > 0, staleTime: 30 * 60_000 }).data;

  const [text, setText] = useState("");
  const [place, setPlace] = useState<Place>("todos");
  const [type, setType] = useState("");
  const [shinyOnly, setShinyOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("quality");
  const [limit, setLimit] = useState(PAGE);
  const [view, setView] = useState<View>("grade");
  const [open, setOpen] = useState<CollectionMon | null>(null);
  const [building, setBuilding] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const { draft, update } = useDraft(accountId, profile);
  const byId = useMemo(() => new Map(all.map((m) => [m.id, m])), [all]);

  useEffect(() => { setView(readView()); }, []);
  const changeView = (v: View) => {
    setView(v);
    try { localStorage.setItem(VIEW_KEY, v); } catch { /* sem armazenamento: só nesta visita */ }
  };

  const counts = useMemo(() => {
    const c: Record<Place, number> = { todos: all.length, equipe: 0, depot: 0, colecao: 0 };
    for (const m of all) c[placeOf(m)] += 1;
    return c;
  }, [all]);

  const shown = useMemo(() => {
    const t = text.trim().toLowerCase();
    const list = all.filter((m) => {
      if (place !== "todos" && placeOf(m) !== place) return false;
      if (shinyOnly && !m.shiny) return false;
      if (type) {
        const tt = m.species_id != null ? types?.get(m.species_id) : undefined;
        if (!tt || (tt[0] !== type && tt[1] !== type)) return false;
      }
      if (t && !`${m.name ?? ""} ${m.nickname ?? ""}`.toLowerCase().includes(t)) return false;
      return true;
    });
    return sortCollection(list, sort);
  }, [all, text, place, type, shinyOnly, sort, types]);

  const sheetMon = open ? all.find((m) => m.id === open.id) ?? open : null;
  const draftIds = building && draft ? new Set(draft.team.filter((x): x is number => x != null)) : null;
  const toggleSelect = (id: number, on: boolean) => setSelected((s) => {
    const next = new Set(s);
    if (on) next.add(id); else next.delete(id);
    return next;
  });
  const filters = (fn: () => void) => () => { fn(); setLimit(PAGE); };

  return (
    <Panel title="Pokémons" meta={q.data ? `${num(all.length)} pokémons` : undefined}
      hint={<>Todos os pokémons da conta. <strong>Equipe</strong>: os 5 que lutam. <strong>Depot</strong>: guardados, vão na
        próxima venda do Depot. <strong>Coleção</strong>: guardados que a venda não leva. Mexer na equipe leva a conta ao
        Pokécenter.</>}>
      <p className="small muted coll-summary">
        {num(profile.pokemon_count)} pokémons · {num(profile.shiny_count)} shiny · {num(profile.dex_caught)} espécies capturadas
        de {num(profile.dex_seen)} vistas
      </p>
      {q.isLoading ? <p className="muted small">Carregando…</p> : all.length === 0 ? (
        <p className="muted small">Os pokémons aparecem depois que o worker gravar o perfil (até 2 minutos depois de conectar).</p>
      ) : (
        <>
          {building && draft ? (
            <TeamBuilder accountId={accountId} profile={profile} draft={draft} update={update} byId={byId} all={all}
              types={types} atlas={atlas} looktypes={looktypes} onClose={() => setBuilding(false)} onOpen={setOpen} />
          ) : (
            <div className="coll-actions">
              <button type="button" className="small" disabled={!draft} onClick={() => setBuilding(true)}>Montar equipe</button>
              <SellDepot accountId={accountId} depot={all.filter((m) => placeOf(m) === "depot")} />
            </div>
          )}
          <div className="coll-controls">
            <input type="search" placeholder="Nome ou apelido" value={text} onChange={(e) => { setText(e.target.value); setLimit(PAGE); }} />
            <div className="segmented" role="radiogroup" aria-label="Local">
              {(Object.keys(PLACE_PT) as Place[]).map((p) => (
                <button key={p} type="button" role="radio" aria-checked={place === p} className={place === p ? "on" : undefined}
                  onClick={filters(() => setPlace(p))}>
                  {PLACE_PT[p]} <span className="muted small num">{num(counts[p])}</span>
                </button>
              ))}
            </div>
            <select value={type} onChange={(e) => { setType(e.target.value); setLimit(PAGE); }} aria-label="Tipo">
              <option value="">Todos os tipos</option>
              {TYPES.map((t) => <option key={t} value={t}>{TYPE_PT[t]}</option>)}
            </select>
            {view === "grade" && (
              <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Ordem">
                {(Object.keys(SORT_PT) as SortKey[]).map((k) => <option key={k} value={k}>Ordem: {SORT_PT[k]}</option>)}
              </select>
            )}
            <label className="dex-mode">
              <input type="checkbox" role="switch" checked={shinyOnly} onChange={(e) => { setShinyOnly(e.target.checked); setLimit(PAGE); }} /> Só shiny
            </label>
            <div className="segmented" role="radiogroup" aria-label="Ver como">
              {(["grade", "tabela"] as View[]).map((v) => (
                <button key={v} type="button" role="radio" aria-checked={view === v} className={view === v ? "on" : undefined}
                  onClick={() => changeView(v)}>{v === "grade" ? "Grade" : "Tabela"}</button>
              ))}
            </div>
            <span className="muted small">{num(shown.length)} na lista</span>
          </div>

          <BatchBar accountId={accountId} selected={selected} byId={byId} onClear={() => setSelected(new Set())} />

          {view === "tabela" ? (
            <MonTable mons={shown.slice(0, Math.max(limit, PAGE * 2))} types={types} atlas={atlas} looktypes={looktypes}
              activeId={profile.active_pokemon_id} draftIds={draftIds} selected={selected} onToggleSelect={toggleSelect}
              onOpen={setOpen} onDraft={building && draft ? (m) => update(toggleInDraft(draft, m.id)) : undefined} />
          ) : (
            <div className="mons mons-small coll-grid">
              {shown.slice(0, limit).map((m) => (
                <div key={m.id} className={`mon ${m.id === profile.active_pokemon_id ? "is-active" : ""} ${m.shiny ? "is-shiny" : ""} ${draftIds?.has(m.id) ? "is-drafted" : ""}`}>
                  <input type="checkbox" className="mon-check" aria-label={`Selecionar ${m.nickname || m.name || "pokémon"}`}
                    checked={selected.has(m.id)} onChange={(e) => toggleSelect(m.id, e.target.checked)} />
                  <button type="button" className="mon-open" onClick={() => setOpen(m)} aria-label={`Ver a ficha de ${m.name ?? "pokémon"}`}>
                    <Sprite mon={m} atlas={atlas} looktypes={looktypes} size={48} />
                    <span className="mon-name">{m.nickname || m.name || `#${m.species_id ?? "?"}`}{m.shiny && <span aria-label="shiny"> ✨</span>}</span>
                    <span className="mon-meta num">nv {m.level ?? "?"}{m.grade != null && <> · N {num(m.grade)}</>}</span>
                    <span className="mon-selos num">
                      {m.quality != null && <span className={`mini-selo tier-${tierQuality(m.quality)}`}>Q {num(m.quality)}</span>}
                      {m.iv_sum != null && <span className={`mini-selo tier-${tierIvSum(m.iv_sum)}`}>IV {m.iv_sum}</span>}
                      {m.potency != null && <span className={`mini-selo tier-${tierPotency(m.potency)}`}>P{m.potency}</span>}
                    </span>
                    <span className="coll-place small muted">
                      {PLACE_PT[placeOf(m)]}{m.slot != null ? ` ${m.slot + 1}` : ""}{m.id === profile.active_pokemon_id ? " · ativo" : ""}
                    </span>
                  </button>
                </div>
              ))}
            </div>
          )}
          {shown.length > (view === "tabela" ? Math.max(limit, PAGE * 2) : limit) && (
            <button type="button" className="ghost small" style={{ marginTop: ".6rem" }} onClick={() => setLimit((l) => Math.max(l, PAGE * 2) + PAGE)}>
              Mostrar mais
            </button>
          )}
        </>
      )}

      {sheetMon && (
        <MonSheet mon={sheetMon} atlas={atlas} looktypes={looktypes} active={sheetMon.id === profile.active_pokemon_id} onClose={() => setOpen(null)}>
          {building && draft && <DraftActions draft={draft} update={update} mon={sheetMon} />}
          <MonActions accountId={accountId} mon={sheetMon} team={profile.team} isActive={sheetMon.id === profile.active_pokemon_id}
            inCollection={!!sheetMon.in_collection} training={training} />
        </MonSheet>
      )}
    </Panel>
  );
}

/** Na ficha, durante a montagem: pôr ou tirar da equipe montada e escolher o ativo dela. */
function DraftActions({ draft, update, mon }: { draft: Draft; update: (d: Draft) => void; mon: CollectionMon }) {
  const inDraft = draft.team.includes(mon.id);
  const full = draft.team.filter((x) => x != null).length >= TEAM_SLOTS;
  return (
    <div className="mon-actions">
      <button type="button" className="small" disabled={!inDraft && full} onClick={() => update(toggleInDraft(draft, mon.id))}>
        {inDraft ? "Tirar da equipe montada" : full ? "Equipe montada cheia" : "Pôr na equipe montada"}
      </button>
      {inDraft && draft.active !== mon.id && (
        <button type="button" className="ghost small" onClick={() => update({ ...draft, active: mon.id })}>Será o ativo</button>
      )}
    </div>
  );
}

/** Ações nos selecionados: guardar na Coleção ou mandar para o Depot (comando em lote). */
function BatchBar({ accountId, selected, byId, onClear }: {
  accountId: string; selected: Set<number>; byId: Map<number, CollectionMon>; onClear: () => void;
}) {
  const { send, cmd, error, busy } = useCommand();
  if (selected.size === 0 && !cmd) return null;
  // quem está na equipe não tem marca de Coleção/Depot que importe agora
  const ids = [...selected].filter((id) => byId.get(id)?.slot == null).slice(0, BATCH_MAX);
  const move = (to: "colecao" | "depot") => void send(accountId, "collection.move", { pokemon_ids: ids, to });
  return (
    <div className="batch-bar">
      {selected.size > 0 && (
        <>
          <span className="small"><strong>{num(selected.size)}</strong> selecionados{ids.length < selected.size ? ` (${ids.length} fora da equipe)` : ""}</span>
          <button type="button" className="small" disabled={busy || ids.length === 0} onClick={() => move("colecao")}>Guardar na Coleção</button>
          <button type="button" className="ghost small" disabled={busy || ids.length === 0} onClick={() => move("depot")}>Mandar para o Depot</button>
          <button type="button" className="ghost small" onClick={onClear}>Limpar</button>
        </>
      )}
      <CommandStatus cmd={cmd} error={error} inline />
    </div>
  );
}
