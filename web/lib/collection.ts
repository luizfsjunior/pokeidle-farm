import type { SupabaseClient } from "@supabase/supabase-js";
import type { Mon } from "@/lib/profile";

/**
 * A coleção completa da conta (account_pokemon; docs/design/conta-v2.md, seção 1.2): equipe, depot e
 * Coleção, um pokémon por linha. O worker atualiza só o que mudou.
 */
export type CollectionMon = Mon & { in_collection?: boolean; folder?: unknown; locked?: unknown; starter?: boolean };

export async function loadCollection(sb: SupabaseClient, accountId: string): Promise<CollectionMon[]> {
  const out: CollectionMon[] = [];
  // em páginas de 1000 (o limite do PostgREST)
  for (let from = 0; ; from += 1000) {
    const { data, error } = await sb.from("account_pokemon").select("pokemon_id, slot, data")
      .eq("account_id", accountId).order("pokemon_id").range(from, from + 999);
    if (error) throw new Error(error.message);
    for (const r of data ?? []) {
      const d = (r.data ?? {}) as CollectionMon;
      out.push({ ...d, id: Number(r.pokemon_id), slot: r.slot ?? null });
    }
    if (!data || data.length < 1000) break;
  }
  return out;
}

export type Place = "todos" | "equipe" | "depot" | "colecao";
export const PLACE_PT: Record<Place, string> = { todos: "Todos", equipe: "Equipe", depot: "Depot", colecao: "Coleção" };

export const placeOf = (m: CollectionMon): Exclude<Place, "todos"> =>
  m.slot != null ? "equipe" : m.in_collection ? "colecao" : "depot";

export type SortKey = "level" | "grade" | "power" | "iv" | "potency" | "quality" | "recent";
export const SORT_PT: Record<SortKey, string> = {
  level: "Nível", grade: "Nota", power: "Poder", iv: "IV total", potency: "Potência", quality: "Qualidade", recent: "Captura mais recente",
};

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : -Infinity);
const caught = (m: CollectionMon) =>
  typeof m.caught_at === "number" ? m.caught_at : typeof m.caught_at === "string" ? Date.parse(m.caught_at) || 0 : 0;

export function sortCollection(list: CollectionMon[], key: SortKey): CollectionMon[] {
  const val = (m: CollectionMon): number => {
    switch (key) {
      case "level": return num(m.level);
      case "grade": return num(m.grade);
      case "power": return num(m.power);
      case "iv": return num(m.iv_sum);
      case "potency": return num(m.potency);
      case "quality": return num(m.quality);
      case "recent": return caught(m);
    }
  };
  return [...list].sort((a, b) => val(b) - val(a) || num(b.level) - num(a.level) || a.id - b.id);
}
