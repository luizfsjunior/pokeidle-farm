"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CommandStatus } from "@/components/CommandStatus";
import { Sprite } from "@/components/Sprite";
import type { CollectionMon } from "@/lib/collection";
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
 * "Montar equipe" (docs/design/conta-v2.md, seção 3): 5 vagas e o ativo. Clicar na coleção põe ou tira;
 * "Aplicar" manda o team.apply, que vai ao Pokécenter, troca, define o ativo e volta para a hunt.
 */
export function TeamBuilder({ accountId, profile, draft, update, byId, atlas, looktypes, onClose }: {
  accountId: string;
  profile: Profile;
  draft: Draft;
  update: (d: Draft) => void;
  byId: Map<number, CollectionMon>;
  atlas: Atlas | null;
  looktypes: Map<number, number>;
  onClose: () => void;
}) {
  const { send, cmd, error, busy } = useCommand();
  const now = useMemo(() => draftFromProfile(profile), [profile]);
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
    return { team, active: draft.active };
  };

  return (
    <div className="builder">
      <div className="builder-head">
        <strong>Montar equipe</strong>
        <span className="muted small">Clique na coleção para pôr ou tirar. ★ escolhe o ativo.</span>
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
                  {m && <Sprite mon={m} atlas={atlas} looktypes={looktypes} size={40} />}
                  <span className="mon-name">{name(id)}</span>
                  <span className="mon-meta num">nv {m?.level ?? "?"}</span>
                  <span className="builder-tools">
                    <button type="button" className="icon" aria-label="Para a esquerda" onClick={() => swap(i, i - 1)} disabled={i === 0}>‹</button>
                    <button type="button" className="icon" aria-label="Tornar ativo" aria-pressed={id === draft.active}
                      onClick={() => update({ ...draft, active: id })}>★</button>
                    <button type="button" className="icon" aria-label="Tirar da vaga" onClick={() => update(toggleInDraft(draft, id))}>×</button>
                    <button type="button" className="icon" aria-label="Para a direita" onClick={() => swap(i, i + 1)} disabled={i === TEAM_SLOTS - 1}>›</button>
                  </span>
                </>
              )}
            </li>
          );
        })}
      </ol>
      {changes.length > 0 ? (
        <ul className="builder-diff small">{changes.map((c) => <li key={c}>{c}</li>)}</ul>
      ) : <p className="muted small">Igual à equipe de agora.</p>}
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
