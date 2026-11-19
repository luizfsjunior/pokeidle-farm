"use client";

import { useMemo, useState } from "react";
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
import { TeamBuilder, toggleInDraft, useDraft } from "./TeamBuilder";
import { MonActions } from "./TeamControls";

const PAGE = 60;

/**
 * A coleção inteira da conta, com busca, local (equipe, depot, Coleção), tipo, shiny e ordem. Clicar abre a
 * ficha, com os botões de equipe (docs/design/conta-v2.md, seção 1.2).
 */
export function Collection({ accountId, profile, atlas, looktypes }: {
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
  const [sort, setSort] = useState<SortKey>("level");
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState<CollectionMon | null>(null);
  const [building, setBuilding] = useState(false);
  const { draft, update } = useDraft(accountId, profile);
  const byId = useMemo(() => new Map(all.map((m) => [m.id, m])), [all]);

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

  return (
    <Panel title="Coleção" meta={q.data ? `${num(all.length)} pokémons` : undefined}
      hint={<>Todos os pokémons da conta: equipe, depot e Coleção. Mexer na equipe só funciona com a conta no Pokécenter
        (o Depot é de lá).</>}>
      {q.isLoading ? <p className="muted small">Carregando a coleção…</p> : all.length === 0 ? (
        <p className="muted small">A coleção aparece depois que o worker novo gravar o perfil (até 2 minutos depois do rebuild).</p>
      ) : (
        <>
          {building && draft ? (
            <TeamBuilder accountId={accountId} profile={profile} draft={draft} update={update} byId={byId}
              atlas={atlas} looktypes={looktypes} onClose={() => setBuilding(false)} />
          ) : (
            <button type="button" className="small" style={{ marginBottom: ".8rem" }} disabled={!draft}
              onClick={() => setBuilding(true)}>Montar equipe</button>
          )}
          <div className="coll-controls">
            <input type="search" placeholder="Nome ou apelido" value={text} onChange={(e) => { setText(e.target.value); setLimit(PAGE); }} />
            <div className="segmented" role="radiogroup" aria-label="Local">
              {(Object.keys(PLACE_PT) as Place[]).map((p) => (
                <button key={p} type="button" role="radio" aria-checked={place === p} className={place === p ? "on" : undefined}
                  onClick={() => { setPlace(p); setLimit(PAGE); }}>
                  {PLACE_PT[p]} <span className="muted small num">{num(counts[p])}</span>
                </button>
              ))}
            </div>
            <select value={type} onChange={(e) => { setType(e.target.value); setLimit(PAGE); }} aria-label="Tipo">
              <option value="">Todos os tipos</option>
              {TYPES.map((t) => <option key={t} value={t}>{TYPE_PT[t]}</option>)}
            </select>
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Ordem">
              {(Object.keys(SORT_PT) as SortKey[]).map((k) => <option key={k} value={k}>Ordem: {SORT_PT[k]}</option>)}
            </select>
            <label className="dex-mode">
              <input type="checkbox" role="switch" checked={shinyOnly} onChange={(e) => { setShinyOnly(e.target.checked); setLimit(PAGE); }} /> Só shiny
            </label>
            <span className="muted small">{num(shown.length)} na lista</span>
          </div>

          <div className="mons mons-small coll-grid">
            {shown.slice(0, limit).map((m) => (
              <div key={m.id} className={`mon ${m.id === profile.active_pokemon_id ? "is-active" : ""} ${m.shiny ? "is-shiny" : ""} ${building && draft?.team.includes(m.id) ? "is-drafted" : ""}`}>
                <button type="button" className="mon-open"
                  onClick={() => (building && draft ? update(toggleInDraft(draft, m.id)) : setOpen(m))}
                  aria-label={building ? `Pôr ou tirar ${m.name ?? "pokémon"} da equipe montada` : `Ver a ficha de ${m.name ?? "pokémon"}`}>
                  <Sprite mon={m} atlas={atlas} looktypes={looktypes} size={48} />
                  <span className="mon-name">{m.nickname || m.name || `#${m.species_id ?? "?"}`}{m.shiny && <span aria-label="shiny"> ✨</span>}</span>
                  <span className="mon-meta num">nv {m.level ?? "?"}{m.grade != null && <> · N {num(m.grade)}</>}</span>
                  <span className="mon-selos num">
                    {m.potency != null && <span className={`mini-selo tier-${tierPotency(m.potency)}`}>P{m.potency}</span>}
                    {m.iv_sum != null && <span className={`mini-selo tier-${tierIvSum(m.iv_sum)}`}>IV {m.iv_sum}</span>}
                    {m.quality != null && <span className={`mini-selo tier-${tierQuality(m.quality)}`}>Q {num(m.quality)}</span>}
                  </span>
                  <span className="coll-place small muted">{PLACE_PT[placeOf(m)]}{m.slot != null ? ` ${m.slot + 1}` : ""}</span>
                </button>
              </div>
            ))}
          </div>
          {shown.length > limit && (
            <button type="button" className="ghost small" style={{ marginTop: ".6rem" }} onClick={() => setLimit((l) => l + PAGE)}>
              Mostrar mais {num(Math.min(PAGE, shown.length - limit))}
            </button>
          )}
        </>
      )}

      {sheetMon && (
        <MonSheet mon={sheetMon} atlas={atlas} looktypes={looktypes} active={sheetMon.id === profile.active_pokemon_id} onClose={() => setOpen(null)}>
          <MonActions accountId={accountId} mon={sheetMon} team={profile.team} isActive={sheetMon.id === profile.active_pokemon_id} />
        </MonSheet>
      )}
    </Panel>
  );
}
