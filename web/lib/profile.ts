import type { SupabaseClient } from "@supabase/supabase-js";

/** Pokémon resumido pelo worker (worker/src/pokeidle_farm/profile.py, `compact_pokemon`). */
export type Mon = {
  id: number;
  species_id?: number;
  name?: string;
  level?: number;
  shiny?: boolean;
  slot?: number | null;
  looktype?: number;
  power?: number;
  quality?: number;
  potency?: number;
  hp?: number;
  max_hp?: number;
  iv_sum?: number;
  ivs?: Record<string, number>;
  stats?: Record<string, number>; // stats de combate, se o jogo mandar
  caught_at?: number | string;
  xp?: number;
  xp_level?: number;
  xp_next?: number;
  nickname?: string;
  skin?: unknown;
  refine?: number | Record<string, number>;
  grade?: number; // a nota que o jogo calcula (0 a 10)
  min_level?: number;
  refine_total?: number;
  tm_elemental?: unknown;
  tm_physical?: unknown;
  tm_aoe?: unknown;
  held_item_id?: number;
  caught_by?: string | boolean;
  gym_level?: number;
};

/** Linha de `account_profile` (docs/design/painel-perfil.md). */
export type Profile = {
  account_id: string;
  updated_at: string;
  level: number | null;
  xp: number | null;
  xp_level: number | null;
  xp_next: number | null;
  gold: number | null;
  gems: number | null;
  diamonds: number | null;
  vip_until: string | null;
  hunt_slug: string | null;
  active_pokemon_id: number | null;
  pokemon_count: number;
  shiny_count: number;
  dex_seen: number;
  dex_caught: number;
  team: Mon[];
  top_pokemon: Mon[];
  shinies: Mon[];
  items: Record<string, number>;
  balls: Record<string, number>;
  estado_keys: string[];
  extra: ProfileExtra;
  pokedex: Record<string, { c?: number; k?: number } | number>;
};

/** Campos do estado guardados como vieram (worker: profile.EXTRA_KEYS). Formatos a mapear. */
export type ProfileExtra = {
  passe?: { degrau?: number; total?: number; ciclos?: number; ultimo?: number; vipAte?: number };
  loja?: { vip?: boolean; vipAte?: number; looktype?: number; gender?: string };
  [key: string]: unknown;
};

/** Dia do jogo (dias desde 1970 no fuso de Brasília), como o `passe.ultimo`. */
export function gameDay(now = Date.now()): number {
  return Math.floor((now - 3 * 3600_000) / 86400_000);
}

export async function loadProfiles(supabase: SupabaseClient, ids: string[]): Promise<Map<string, Profile>> {
  if (ids.length === 0) return new Map();
  const { data } = await supabase.from("account_profile").select("*").in("account_id", ids);
  return new Map(((data ?? []) as Profile[]).map((p) => [p.account_id, p]));
}

/** O pokémon ativo: o da equipe com o id ativo, senão o primeiro da equipe. */
export function activeMon(p: Profile | undefined): Mon | undefined {
  if (!p) return undefined;
  return p.team.find((m) => m.id === p.active_pokemon_id) ?? p.team[0];
}

/**
 * Progresso dentro do nível (0–1). O jogo manda o XP total (`xp`), o XP em que o nível atual começa
 * (`xpNivel`) e o do próximo (`xpProximo`); sem os dois limites, não há barra.
 */
export function levelProgress(p: Profile): number | null {
  const { xp, xp_level: from, xp_next: to } = p;
  if (xp == null || from == null || to == null || to <= from) return null;
  return Math.min(1, Math.max(0, (xp - from) / (to - from)));
}

/** Espécies do perfil (equipe, destaques, shinies) para buscar o looktype na Pokedex. */
export function speciesOf(...lists: Mon[][]): number[] {
  const out = new Set<number>();
  for (const list of lists) for (const m of list) if (m.species_id != null && m.looktype == null) out.add(m.species_id);
  return [...out];
}
