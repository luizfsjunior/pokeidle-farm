"use client";

import { useMemo, useState } from "react";
import { Sprite } from "@/components/Sprite";
import { TypeChip } from "@/components/SpeciesFacts";
import { placeOf, PLACE_PT, type CollectionMon } from "@/lib/collection";
import { num } from "@/lib/format";
import { STAT_LABEL, STATS, type Stat } from "@/lib/pokemon";
import type { Atlas } from "@/lib/sprites";

/**
 * Tabela de comparação (docs/design/refatoracao-2026-11-20.md, 4.2): para escolher a equipe sem decorar os
 * números. Colunas ordenáveis; a ordem inicial é Qualidade, depois Nota (o que o usuário olha primeiro). O
 * melhor valor de cada coluna, na lista filtrada, fica destacado.
 */
type Col = {
  id: string;
  label: string;
  title?: string;
  value: (m: CollectionMon) => number | null;
  fmt?: (v: number) => string;
};

const n = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const dec = (v: number) => num(v);
const STAT_SHORT: Record<Stat, string> = { hp: "HP", atk: "Atk", def: "Def", spAtk: "SpA", spDef: "SpD", speed: "Vel" };

const COLS: Col[] = [
  { id: "quality", label: "Q", title: "Qualidade", value: (m) => n(m.quality), fmt: dec },
  { id: "grade", label: "Nota", value: (m) => n(m.grade), fmt: dec },
  { id: "iv", label: "IV", title: "IV total", value: (m) => n(m.iv_sum) },
  ...STATS.map((s): Col => ({ id: `iv_${s}`, label: STAT_SHORT[s], title: `IV de ${STAT_LABEL[s]}`, value: (m) => n(m.ivs?.[s]) })),
  ...STATS.map((s): Col => ({ id: `st_${s}`, label: STAT_SHORT[s], title: `${STAT_LABEL[s]} (stat de combate)`, value: (m) => n(m.stats?.[s]) })),
  { id: "level", label: "Nv", title: "Nível", value: (m) => n(m.level) },
  { id: "potency", label: "P", title: "Potência", value: (m) => n(m.potency) },
];
const DEFAULT_SORT = ["quality", "grade"];

export function MonTable({ mons, types, atlas, looktypes, activeId, draftIds, selected, onToggleSelect, onOpen, onDraft }: {
  mons: CollectionMon[];
  types: Map<number, [string, string | null]> | undefined;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  activeId: number | null;
  draftIds: Set<number> | null; // montando a equipe: quem está nas vagas
  selected: Set<number>;
  onToggleSelect: (id: number, on: boolean) => void;
  onOpen: (m: CollectionMon) => void;
  onDraft?: (m: CollectionMon) => void;
}) {
  const [sort, setSort] = useState<{ id: string; asc: boolean } | null>(null);
  const rows = useMemo(() => {
    const keys = sort ? [sort.id] : DEFAULT_SORT;
    const dir = sort?.asc ? 1 : -1;
    const val = (m: CollectionMon, id: string) => COLS.find((c) => c.id === id)!.value(m) ?? -Infinity;
    return [...mons].sort((a, b) => {
      for (const k of keys) {
        const d = (val(a, k) - val(b, k)) * dir;
        if (d) return d;
      }
      return a.id - b.id;
    });
  }, [mons, sort]);
  const best = useMemo(() => {
    const out = new Map<string, number>();
    for (const c of COLS) {
      const vs = mons.map(c.value).filter((v): v is number => v != null);
      if (vs.length > 1) out.set(c.id, Math.max(...vs));
    }
    return out;
  }, [mons]);
  const hasStats = mons.some((m) => m.stats && Object.keys(m.stats).length > 0);
  const cols = COLS.filter((c) => hasStats || !c.id.startsWith("st_"));
  const allOn = rows.length > 0 && rows.every((m) => selected.has(m.id));

  const header = (c: Col, rowSpan?: number) => {
    const on = sort?.id === c.id || (!sort && c.id === "quality");
    const dir = sort?.id === c.id ? (sort.asc ? "ascending" : "descending") : !sort && c.id === "quality" ? "descending" : "none";
    return (
      <th key={c.id} rowSpan={rowSpan} className={`r ${c.id.startsWith("st_") ? "col-stat" : c.id.startsWith("iv_") ? "col-iv" : ""}`} aria-sort={dir}>
        <button type="button" className={`th-sort ${on ? "is-on" : ""}`} title={c.title ?? c.label}
          onClick={() => setSort(sort?.id === c.id ? { id: c.id, asc: !sort.asc } : { id: c.id, asc: false })}>
          {c.label}{on ? (sort?.asc ? " ↑" : " ↓") : ""}
        </button>
      </th>
    );
  };

  return (
    <div className="table-scroll mon-table-wrap">
      <table className="mon-table" data-keep>
        <thead>
          <tr>
            <th className="col-sel" rowSpan={2}>
              <input type="checkbox" aria-label="Selecionar todos da lista" checked={allOn}
                onChange={(e) => rows.forEach((m) => onToggleSelect(m.id, e.target.checked))} />
            </th>
            <th rowSpan={2}>Pokémon</th>
            <th rowSpan={2}>Tipos</th>
            {cols.slice(0, 3).map((c) => header(c, 2))}
            <th colSpan={6} className="group-head col-iv">IVs</th>
            {hasStats && <th colSpan={6} className="group-head col-stat">Stats</th>}
            {cols.slice(-2).map((c) => header(c, 2))}
            {onDraft && <th rowSpan={2} aria-label="Equipe" />}
          </tr>
          <tr className="sub-head">
            {cols.filter((c) => c.id.startsWith("iv_") || c.id.startsWith("st_")).map((c) => header(c))}
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => {
            const t = m.species_id != null ? types?.get(m.species_id) : undefined;
            const drafted = draftIds?.has(m.id) ?? false;
            return (
              <tr key={m.id} className={`${m.id === activeId ? "is-active" : ""} ${drafted ? "is-drafted" : ""}`}>
                <td className="col-sel">
                  <input type="checkbox" aria-label={`Selecionar ${m.nickname || m.name || m.id}`} checked={selected.has(m.id)}
                    onChange={(e) => onToggleSelect(m.id, e.target.checked)} />
                </td>
                <td>
                  <button type="button" className="mon-cell" onClick={() => onOpen(m)} title="Abrir a ficha">
                    <Sprite mon={m} atlas={atlas} looktypes={looktypes} size={32} />
                    <span>
                      <span className="mon-name">{m.nickname || m.name || `#${m.species_id ?? "?"}`}{m.shiny && " ✨"}</span>
                      <span className="small muted">{PLACE_PT[placeOf(m)]}{m.slot != null ? ` ${m.slot + 1}` : ""}{m.id === activeId ? " · ativo" : ""}</span>
                    </span>
                  </button>
                </td>
                <td className="col-types">{t ? [t[0], t[1]].filter((x): x is string => !!x).map((x) => <TypeChip key={x} type={x} />) : "—"}</td>
                {cols.map((c) => {
                  const v = c.value(m);
                  const top = v != null && best.get(c.id) === v;
                  return (
                    <td key={c.id} className={`r num ${top ? "is-best" : ""} ${c.id.startsWith("st_") ? "col-stat" : c.id.startsWith("iv_") ? "col-iv" : ""}`}>
                      {v == null ? "—" : c.fmt ? c.fmt(v) : num(v)}
                    </td>
                  );
                })}
                {onDraft && (
                  <td>
                    <button type="button" className={`small ${drafted ? "ghost" : ""}`} onClick={() => onDraft(m)}>
                      {drafted ? "Tirar" : "Pôr"}
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
