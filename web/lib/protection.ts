import type { SupabaseClient } from "@supabase/supabase-js";
import type { CollectionMon } from "@/lib/collection";

/**
 * Pokémon protegidos (épico C1, docs/design/protegidos-e-bosses.md): nenhuma automação vende, manda para o
 * Depot, oferece, sacrifica ou troca. A mesma regra do worker (worker/src/pokeidle_farm/protection.py):
 * marcado aqui no painel, shiny, na equipe ou na Coleção do jogo. Só a marca manual fica na tabela
 * `protected_pokemon`; o painel grava e apaga direto (RLS do dono) e o worker relê em até 1 minuto.
 */
export type Reason = "manual" | "shiny" | "equipe" | "colecao";
export const REASON_PT: Record<Reason, string> = {
  manual: "marcado no painel",
  shiny: "shiny",
  equipe: "na equipe",
  colecao: "na Coleção do jogo",
};

export async function loadProtected(sb: SupabaseClient, accountId: string): Promise<Set<number>> {
  const { data, error } = await sb.from("protected_pokemon").select("pokemon_id").eq("account_id", accountId);
  if (error) throw new Error(error.message);
  return new Set((data ?? []).map((r) => Number(r.pokemon_id)));
}

export async function setProtected(sb: SupabaseClient, accountId: string, ids: number[], on: boolean): Promise<void> {
  if (ids.length === 0) return;
  const { error } = on
    ? await sb.from("protected_pokemon").upsert(ids.map((pokemon_id) => ({ account_id: accountId, pokemon_id })),
      { onConflict: "account_id,pokemon_id", ignoreDuplicates: true })
    : await sb.from("protected_pokemon").delete().eq("account_id", accountId).in("pokemon_id", ids);
  if (error) throw new Error(error.message);
}

export function reasonsOf(m: CollectionMon, manual: Set<number> | undefined): Reason[] {
  const out: Reason[] = [];
  if (manual?.has(m.id)) out.push("manual");
  if (m.shiny) out.push("shiny");
  if (m.slot != null) out.push("equipe");
  if (m.in_collection) out.push("colecao");
  return out;
}

/** Shiny ou marcado no painel: nem o painel manda para o Depot (a Coleção é a marca que você mesmo mexe). */
export const keepsOutOfDepot = (m: CollectionMon, manual: Set<number> | undefined) => !!m.shiny || !!manual?.has(m.id);

export const reasonsText = (rs: Reason[]) => rs.map((r) => REASON_PT[r]).join(", ");
