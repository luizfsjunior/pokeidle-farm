import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Dados do painel de hunts: catálogo do jogo, pedras de cada espécie e o preço delas.
 * O modelo das pedras é o mesmo do worker (worker/src/pokeidle_farm/gems_model.py): cada
 * selvagem dropa a pedra de cada tipo seu com 0,2% / 0,35% / 0,5% por abate conforme a posição
 * na cadeia evolutiva; as constantes vêm de `game_catalog.loot_stones` (lidas do código do jogo).
 */

export type Species = { species_id: number; name: string | null; type1: string | null; type2: string | null; evolves_to: number | null };
export type CatalogHunt = { slug: string; name: string | null; level: number; area: string | null; region: string | null; species_id: number; species_name: string | null };
export type Stone = { name: string; chance: number; gems: number | null; soldWeek: number | null };

const DEFAULT_CHANCES: [number, number, number] = [0.002, 0.0035, 0.005];
const DEFAULT_BY_TYPE: Record<string, string> = {
  NORMAL: "Sun Stone", FIRE: "Fire Stone", WATER: "Water Stone", GRASS: "Leaf Stone", ELECTRIC: "Thunder Stone",
  ICE: "Ice Stone", FIGHTING: "Punch Stone", POISON: "Venom Stone", GROUND: "Earth Stone", FLYING: "Feather Stone",
  PSYCHIC: "Enigma Stone", BUG: "Cocoon Stone", ROCK: "Rock Stone", GHOST: "Darkness Stone", DRAGON: "Ancient Stone",
  DARK: "Darkness Stone", STEEL: "Metal Stone", FAIRY: "Heart Stone",
};

export async function loadAllSpecies(supabase: SupabaseClient): Promise<Map<number, Species>> {
  const out = new Map<number, Species>();
  for (let from = 0; ; from += 1000) {
    const { data } = await supabase.from("game_species")
      .select("species_id, name, type1, type2, evolves_to").order("species_id").range(from, from + 999);
    for (const s of (data ?? []) as Species[]) out.set(s.species_id, s);
    if (!data || data.length < 1000) return out;
  }
}

export async function loadLootStones(supabase: SupabaseClient) {
  const { data } = await supabase.from("game_catalog").select("data").eq("key", "loot_stones").maybeSingle();
  const d = (data?.data ?? {}) as { chance_by_position?: number[]; stone_by_type?: Record<string, string> };
  const chances = Array.isArray(d.chance_by_position) && d.chance_by_position.length === 3
    ? (d.chance_by_position as [number, number, number]) : DEFAULT_CHANCES;
  return { chances, byType: d.stone_by_type && Object.keys(d.stone_by_type).length ? d.stone_by_type : DEFAULT_BY_TYPE };
}

/** Preço médio em gemas e vendidas por semana, por nome de item (último snapshot). */
export async function loadStonePrices(supabase: SupabaseClient) {
  const out = new Map<string, { gems: number; soldWeek: number }>();
  const last = await supabase.from("market_prices").select("taken_at").order("taken_at", { ascending: false }).limit(1).maybeSingle();
  if (!last.data) return { prices: out, takenAt: null as string | null };
  const takenAt = last.data.taken_at as string;
  const rows = await supabase.from("market_prices").select("item_id, avg, units, days").eq("taken_at", takenAt).eq("currency", "orb");
  const ids = (rows.data ?? []).map((r) => r.item_id as number);
  const items = ids.length ? await supabase.from("game_items").select("item_id, name").in("item_id", ids) : { data: [] };
  const names = new Map(((items.data ?? []) as { item_id: number; name: string }[]).map((i) => [i.item_id, i.name]));
  for (const r of (rows.data ?? []) as { item_id: number; avg: number; units: number | null; days: number | null }[]) {
    const name = names.get(r.item_id);
    if (name) out.set(name, { gems: Number(r.avg), soldWeek: ((Number(r.units) || 0) * 7) / (r.days || 7) });
  }
  return { prices: out, takenAt };
}

/** Posição na cadeia como o `estagioDaPedra` do jogo: 0, 1 ou 2; sem evolução conta como 2. */
export function chainPosition(species: Map<number, Species>, parents: Map<number, number>, id: number): number {
  const sp = species.get(id);
  if (!sp) return 2;
  let depth = 0;
  let cur = id;
  const seen = new Set<number>();
  while (parents.has(cur) && !seen.has(cur)) {
    seen.add(cur);
    cur = parents.get(cur)!;
    depth++;
  }
  if (depth === 0 && !sp.evolves_to) return 2;
  return Math.min(depth, 2);
}

export function parentsOf(species: Map<number, Species>): Map<number, number> {
  const parents = new Map<number, number>();
  for (const s of species.values()) if (s.evolves_to && !parents.has(s.evolves_to)) parents.set(s.evolves_to, s.species_id);
  return parents;
}

export function stonesOf(
  sp: Species | undefined,
  byType: Record<string, string>,
  chance: number,
  prices: Map<string, { gems: number; soldWeek: number }>,
): Stone[] {
  const out: Stone[] = [];
  for (const t of [sp?.type1, sp?.type2]) {
    const name = t ? byType[t.toUpperCase()] : undefined;
    if (!name || out.some((s) => s.name === name)) continue;
    const p = prices.get(name);
    out.push({ name, chance, gems: p?.gems ?? null, soldWeek: p?.soldWeek ?? null });
  }
  return out;
}

/** Gemas por 1.000 abates (não depende do ritmo). */
export const gemsPer1000 = (stones: Stone[]) => stones.reduce((s, x) => s + 1000 * x.chance * (x.gems ?? 0), 0);
