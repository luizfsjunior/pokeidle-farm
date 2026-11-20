"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { TypeChip } from "@/components/SpeciesFacts";
import { Sprite } from "@/components/Sprite";
import type { CollectionMon } from "@/lib/collection";
import { num } from "@/lib/format";
import type { Profile } from "@/lib/profile";
import { supabaseBrowser, usePanel } from "@/lib/query/hooks";
import type { Atlas } from "@/lib/sprites";
import { useCommand } from "@/lib/useCommand";

export const TEAM_SLOTS = 5;

export type Draft = { team: (number | null)[]; active: number | null };

type DraftRow = { team: (number | string | null)[] | null; active_id: number | string | null };

async function loadDraft(sb: ReturnType<typeof supabaseBrowser>, accountId: string): Promise<Draft | null> {
  const { data, error } = await sb.from("team_drafts").select("team, active_id").eq("account_id", accountId)
    .maybeSingle<DraftRow>();
  if (error) throw new Error(error.message);
  if (!data) return null;
  const team = Array.from({ length: TEAM_SLOTS }, (_, i) => (data.team?.[i] == null ? null : Number(data.team[i])));
  return { team, active: data.active_id == null ? null : Number(data.active_id) };
}

/** A equipe de agora como rascunho: vaga -> id. */
export function draftFromProfile(profile: Profile): Draft {
  const team: (number | null)[] = Array.from({ length: TEAM_SLOTS }, () => null);
  for (const m of profile.team) if (typeof m.slot === "number" && m.slot < TEAM_SLOTS) team[m.slot] = m.id;
  return { team, active: profile.active_pokemon_id ?? null };
}

/** Rascunho salvo no banco (team_drafts), um por conta; começa igual à equipe de agora. */
export function useDraft(accountId: string, profile: Profile) {
  const q = usePanel(["team-draft", accountId], (sb) => loadDraft(sb, accountId), { staleTime: Infinity });
  const [draft, setDraft] = useState<Draft | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (draft === null && q.isFetched) setDraft(q.data ?? draftFromProfile(profile));
  }, [draft, q.isFetched, q.data, profile]);

  const update = (next: Draft) => {
    setDraft(next);
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      void supabaseBrowser().from("team_drafts").upsert(
        { account_id: accountId, team: next.team, active_id: next.active, updated_at: new Date().toISOString() },
        { onConflict: "account_id" },
      );
    }, 600);
  };
  return { draft, update };
}

/** Põe ou tira um pokémon do rascunho (primeira vaga livre); o primeiro a entrar vira o ativo. */
export function toggleInDraft(d: Draft, id: number): Draft {
  const at = d.team.indexOf(id);
  if (at >= 0) {
    const team = d.team.map((x) => (x === id ? null : x));
    return { team, active: d.active === id ? team.find((x): x is number => x != null) ?? null : d.active };
  }
  const free = d.team.indexOf(null);
  if (free < 0) return d;
  const team = d.team.map((x, i) => (i === free ? id : x));
  return { team, active: d.active ?? id };
}

/**
 * Sugestão de equipe (refatoracao-2026-11-20, 4.2): o ativo fica, e as outras vagas vão para os melhores por
 * Qualidade e depois Nota, um por espécie.
 */
export function suggestDraft(d: Draft, all: CollectionMon[]): Draft {
  const keep = d.active != null ? all.find((m) => m.id === d.active) : undefined;
  const picked: CollectionMon[] = keep ? [keep] : [];
  const species = new Set(picked.map((m) => m.species_id));
  const ranked = [...all].sort((a, b) => (b.quality ?? 0) - (a.quality ?? 0) || (b.grade ?? 0) - (a.grade ?? 0) || a.id - b.id);
  for (const m of ranked) {
    if (picked.length >= TEAM_SLOTS) break;
    if (species.has(m.species_id) || picked.includes(m)) continue;
    picked.push(m);
    species.add(m.species_id);
  }
  const team = Array.from({ length: TEAM_SLOTS }, (_, i) => picked[i]?.id ?? null);
  return { team, active: keep?.id ?? team[0] };
}

const avg = (xs: (number | undefined)[]) => {
  const v = xs.filter((x): x is number => typeof x === "number");
  return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
};

function SlotTypes({ m, types }: { m: CollectionMon | undefined; types: Map<number, [string, string | null]> | undefined }) {
  const t = m?.species_id != null ? types?.get(m.species_id) : undefined;
  if (!t) return null;
  return <span className="builder-types">{[t[0], t[1]].filter((x): x is string => !!x).map((x) => <TypeChip key={x} type={x} />)}</span>;
}

/**
 * "Montar equipe" (docs/design/conta-v2.md, seção 3, e refatoracao-2026-11-20, 4.2): 5 vagas e o ativo, fixas
 * no topo enquanto a lista rola. Escolher é pela ficha ou pela tabela; "Aplicar" manda o team.apply, que vai ao
 * Pokécenter, troca, define o ativo e volta para a hunt.
 */
export function TeamBuilder({ accountId, profile, draft, update, byId, all, types, atlas, looktypes, onClose, onOpen }: {
  accountId: string;
  profile: Profile;
  draft: Draft;
  update: (d: Draft) => void;
  byId: Map<number, CollectionMon>;
  all: CollectionMon[];
  types: Map<number, [string, string | null]> | undefined;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  onClose: () => void;
  onOpen: (m: CollectionMon) => void;
}) {
  const { send, cmd, error, busy } = useCommand();
  const now = useMemo(() => draftFromProfile(profile), [profile]);
  // quem sai da equipe: para onde vai (padrão Coleção, que a venda do Depot não leva)
  const [leftTo, setLeftTo] = useState<Record<number, "colecao" | "depot">>({});
  const leaving = now.team.filter((id): id is number => id != null && !draft.team.includes(id));
  const name = (id: number | null) => (id == null ? "vazia" : byId.get(id)?.nickname || byId.get(id)?.name || `#${id}`);

  const changes = useMemo(() => {
    const out: string[] = [];
    draft.team.forEach((id, i) => {
      if (id !== now.team[i]) out.push(`Vaga ${i + 1}: ${name(now.team[i])} → ${name(id)}`);
    });
    if (draft.active !== now.active) out.push(`Ativo: ${name(now.active)} → ${name(draft.active)}`);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, now, byId]);

  const filled = draft.team.filter((x) => x != null).length;
  const sum = (d: Draft) => {
    const ms = d.team.map((id) => (id != null ? byId.get(id) : undefined)).filter((m): m is CollectionMon => !!m);
    return { q: avg(ms.map((m) => m.quality)), g: avg(ms.map((m) => m.grade)), iv: avg(ms.map((m) => m.iv_sum)) };
  };
  const before = sum(now);
  const after = sum(draft);
  const cmp = (label: string, a: number | null, b: number | null) => (
    <span>
      {label} {a == null ? "—" : num(a)}
      {a !== b && <> → <strong className={b != null && a != null && b < a ? "warn-text" : "good-text"}>{b == null ? "—" : num(b)}</strong></>}
    </span>
  );
  const canApply = filled > 0 && draft.active != null && draft.team.includes(draft.active) && changes.length > 0;
  const swap = (i: number, j: number) => {
    if (j < 0 || j >= TEAM_SLOTS) return;
    const team = [...draft.team];
    [team[i], team[j]] = [team[j], team[i]];
    update({ ...draft, team });
  };
  // o jogo recebe as vagas em ordem; vazias no fim não precisam ir
  const payload = () => {
    const team = [...draft.team];
    while (team.length && team[team.length - 1] == null) team.pop();
    const left_to = Object.fromEntries(leaving.map((id) => [String(id), leftTo[id] ?? "colecao"]));
    return { team, active: draft.active, left_to };
  };

  return (
    <div className="builder builder-sticky">
      <div className="builder-head">
        <strong>Montar equipe</strong>
        <span className="muted small">Abra um pokémon (ou use a tabela) para pôr ou tirar.</span>
        <button type="button" className="ghost small" onClick={() => update(suggestDraft(draft, all))}
          title="Mantém o ativo e completa com os melhores por Qualidade e Nota, um por espécie">Sugerir</button>
        <button type="button" className="ghost small" onClick={() => update(now)} disabled={changes.length === 0}>Voltar ao atual</button>
        <button type="button" className="ghost small" onClick={onClose}>Fechar</button>
      </div>
      <ol className="builder-slots">
        {draft.team.map((id, i) => {
          const m = id != null ? byId.get(id) : undefined;
          return (
            <li key={i} className={`builder-slot ${id == null ? "is-empty" : ""} ${id != null && id === draft.active ? "is-active" : ""} ${id !== now.team[i] ? "is-changed" : ""}`}>
              {id == null ? <span className="muted small">Vaga {i + 1} vazia</span> : (
                <>
                  <button type="button" className="builder-mon" onClick={() => m && onOpen(m)} title="Abrir a ficha">
                    {m && <Sprite mon={m} atlas={atlas} looktypes={looktypes} size={40} />}
                    <span className="mon-name">{name(id)}</span>
                    {id === draft.active && <span className="badge ready">ativo</span>}
                    <span className="mon-meta num">nv {m?.level ?? "?"}</span>
                    <SlotTypes m={m} types={types} />
                    <span className="mon-meta num">
                      Q {m?.quality != null ? num(m.quality) : "—"} · N {m?.grade != null ? num(m.grade) : "—"} · IV {m?.iv_sum ?? "—"}
                    </span>
                  </button>
                  <span className="builder-tools">
                    <button type="button" className="ghost small" aria-label="Para a esquerda" onClick={() => swap(i, i - 1)} disabled={i === 0}>‹</button>
                    {id !== draft.active && (
                      <button type="button" className="ghost small" onClick={() => update({ ...draft, active: id })}>Ativo</button>
                    )}
                    <button type="button" className="ghost small" onClick={() => update(toggleInDraft(draft, id))}>Tirar</button>
                    <button type="button" className="ghost small" aria-label="Para a direita" onClick={() => swap(i, i + 1)} disabled={i === TEAM_SLOTS - 1}>›</button>
                  </span>
                </>
              )}
            </li>
          );
        })}
      </ol>
      <div className="builder-summary small">
        <span className="muted">Média da equipe:</span>
        {cmp("Q", before.q, after.q)}
        {cmp("Nota", before.g, after.g)}
        {cmp("IV", before.iv, after.iv)}
      </div>
      {changes.length > 0 ? (
        <ul className="builder-diff small">{changes.map((c) => <li key={c}>{c}</li>)}</ul>
      ) : <p className="muted small">Igual à equipe de agora.</p>}
      {leaving.length > 0 && (
        <div className="builder-leaving small">
          <span className="muted">Quem sai vai para:</span>
          {leaving.map((id) => (
            <label key={id}>
              {name(id)}{" "}
              <select value={leftTo[id] ?? "colecao"}
                onChange={(e) => setLeftTo({ ...leftTo, [id]: e.target.value as "colecao" | "depot" })}>
                <option value="colecao">Coleção</option>
                <option value="depot">Depot (vai na venda)</option>
              </select>
            </label>
          ))}
        </div>
      )}
      <div className="builder-foot">
        <button type="button" disabled={!canApply || busy} onClick={() => void send(accountId, "team.apply", payload())}>
          {busy ? "Aplicando…" : "Aplicar"}
        </button>
        <span className="muted small">A conta vai ao Pokécenter, faz as trocas e volta para a hunt (uns 30 s a 1 min).</span>
        <CommandStatus cmd={cmd} error={error} inline />
      </div>
    </div>
  );
}
