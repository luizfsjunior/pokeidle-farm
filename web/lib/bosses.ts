import type { SupabaseClient } from "@supabase/supabase-js";
import { effectiveness, type GameRules } from "@/lib/pokemon";
import type { Mon } from "@/lib/profile";

/**
 * Os bosses lendários (shared/bosses-lendarios.mjs, lido em 17/11): um trio fixo por região, a região
 * pede um nível mínimo e o prêmio de cada boss do trio gira todo dia entre TM, Mega e tickets.
 * Ver docs/design/foco-outland.md (economia dos bosses) e docs/design/bosses-painel.md.
 */
export const BOSS_REGIONS = [
  { region: "kanto", name: "Kanto", trio: "Trio Aves Lendárias", ids: [144, 146, 145] },
  { region: "johto", name: "Johto", trio: "Trio Bestas Lendárias", ids: [245, 244, 243] },
  { region: "hoenn", name: "Hoenn", trio: "Trio Climático", ids: [383, 382, 384] },
  { region: "sinnoh", name: "Sinnoh", trio: "Trio da Criação", ids: [483, 484, 487] },
  { region: "unova", name: "Unova", trio: "Trio Tao", ids: [643, 644, 646] },
  { region: "kalos", name: "Kalos", trio: "Trio da Aura", ids: [716, 717, 718] },
  { region: "alola", name: "Alola", trio: "Trio da Luz", ids: [791, 792, 800] },
  { region: "galar", name: "Galar", trio: "Trio do Combate", ids: [8888, 8889, 890] },
  { region: "paldea", name: "Paldea", trio: "Trio da Lealdade", ids: [1014, 1015, 1016] },
] as const;

export const PRIZES = ["tm", "mega", "tickets"] as const;
export type Prize = (typeof PRIZES)[number];
export const PRIZE_PT: Record<Prize, string> = { tm: "TM", mega: "Fragmento de Mega", tickets: "Tickets" };
const ROTATION_DAY_ZERO = "2026-11-17"; // ROTACAO_BOSS_DIA_ZERO

/** nivelMinimoDoPar: Kanto 300, Johto 650, depois 300 + 350 × degrau³. */
export function bossLevel(step: number): number {
  if (step <= 0) return 300;
  if (step === 1) return 650;
  return 300 + Math.round(350 * step ** 3);
}

/** Chances por vitória que o jogo publica, por degrau (região). */
export const prizeChances = (step: number) => ({
  tm: 0.005 * (step + 1),
  mega: ((step + 1) * 65) / 10_000,
  megaShiny: ((step + 1) * 50) / 10_000,
});

// o "dia sazonal" do jogo vira às 18:00 de Brasília (dia-sazonal.mjs: fuso de Brasília adiantado
// 6 h; a wiki confirma "o prêmio gira dentro da trinca todo dia às 18:00"): 21:00 UTC
const SHIFT = 3 * 3600_000;
const DAY = 86_400_000;
const dayIndex = (t: number) => Math.floor((t + SHIFT) / DAY);

/** O prêmio do boss na posição `pos` do trio, no instante `t` (premioDoBossNoInstante). */
export function prizeAt(pos: number, t = Date.now()): Prize {
  const d = dayIndex(t) - Math.round(Date.parse(`${ROTATION_DAY_ZERO}T00:00:00Z`) / DAY);
  const n = PRIZES.length;
  return PRIZES[(((pos - d) % n) + n) % n];
}

/** Quando o prêmio gira de novo (próximas 18:00 de Brasília). */
export const nextRotation = (t = Date.now()) => (dayIndex(t) + 1) * DAY - SHIFT;

// --- espécies -------------------------------------------------------------------------------------

export type BossSpecies = { species_id: number; name: string; type1: string; type2: string | null; looktype: number | null };

export async function loadBossSpecies(sb: SupabaseClient): Promise<Map<number, BossSpecies>> {
  const ids = BOSS_REGIONS.flatMap((r) => r.ids as readonly number[]);
  const { data, error } = await sb.from("game_species").select("species_id, name, type1, type2, looktype:data->looktype").in("species_id", ids);
  if (error) throw new Error(error.message);
  return new Map(((data ?? []) as BossSpecies[]).map((s) => [Number(s.species_id), { ...s, species_id: Number(s.species_id) }]));
}

/** Tipos das espécies dos pokémons da conta (o perfil não guarda o tipo). */
export async function loadTypes(sb: SupabaseClient, ids: number[]): Promise<Map<number, [string, string | null]>> {
  if (ids.length === 0) return new Map();
  const { data } = await sb.from("game_species").select("species_id, type1, type2").in("species_id", ids);
  return new Map((data ?? []).map((r) => [Number(r.species_id), [r.type1 as string, (r.type2 as string) ?? null]]));
}

// --- quem da conta serve contra o boss ------------------------------------------------------------

export type Candidate = { mon: Mon; hits: number; takes: number; levelOk: boolean };

/**
 * Para cada pokémon: o melhor multiplicador dos tipos dele contra o boss (`hits`) e o pior que ele
 * leva dos tipos do boss (`takes`, supondo que os golpes do boss saem no tipo dele).
 */
export function candidates(mons: Mon[], types: Map<number, [string, string | null]>, boss: BossSpecies, level: number, rules: GameRules): Candidate[] {
  const out: Candidate[] = [];
  for (const mon of mons) {
    const t = mon.species_id != null ? types.get(mon.species_id) : undefined;
    if (!t) continue;
    const own = [t[0], t[1]].filter((x): x is string => !!x);
    const hits = Math.max(...own.map((a) => effectiveness(rules.types, a, boss.type1, boss.type2)));
    const theirs = [boss.type1, boss.type2].filter((x): x is string => !!x);
    const takes = Math.max(...theirs.map((a) => effectiveness(rules.types, a, t[0], t[1])));
    out.push({ mon, hits, takes, levelOk: (mon.level ?? 0) >= level });
  }
  return out.sort((a, b) =>
    Number(b.levelOk) - Number(a.levelOk) || b.hits - a.hits || a.takes - b.takes || (b.mon.power ?? 0) - (a.mon.power ?? 0));
}
