import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Regras do jogo para a ficha do pokémon e da espécie (docs/design/ficha-pokemon.md): tipos, nota,
 * alcance no PvP. Fontes: `game_catalog.regras` (tabela de tipos) e os módulos do jogo em `game_files`
 * (`nota-pokemon.mjs`, `pvp-tabuleiro.mjs`), que o worker sincroniza.
 */

export const STATS = ["hp", "atk", "def", "spAtk", "spDef", "speed"] as const;
export type Stat = (typeof STATS)[number];
export const STAT_LABEL: Record<Stat, string> = { hp: "HP", atk: "Ataque", def: "Defesa", spAtk: "Sp. Atk", spDef: "Sp. Def", speed: "Speed" };
const BASE_KEY: Record<Stat, string> = { hp: "baseHp", atk: "baseAtk", def: "baseDef", spAtk: "baseSpAtk", spDef: "baseSpDef", speed: "baseSpeed" };
export const IV_MAX_STAT = 32;

export type Attack = { name: string; type: string; power: number; category?: string; cooldownMs?: number; learnLevel?: number; tm?: string };

/** Uma espécie com o que a ficha usa (game_species + o JSON do jogo em `data`). */
export type SpeciesInfo = {
  species_id: number;
  name: string | null;
  type1: string | null;
  type2: string | null;
  rarity: string | null;
  evolves_to: number | null;
  evolve_level: number | null;
  hunt_level: number | null;
  looktype: number | null;
  base: Record<Stat, number> | null;
  attacks: Attack[];
  description: string | null;
  experience: number | null;
  price_npc: number | null;
  parents: { species_id: number; name: string | null }[]; // quem evolui para esta espécie
  evolves_to_name: string | null;
};

type Obj = Record<string, unknown>;
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function baseOf(d: Obj): Record<Stat, number> | null {
  const out = {} as Record<Stat, number>;
  for (const s of STATS) {
    const v = num(d[BASE_KEY[s]]);
    if (v == null) return null;
    out[s] = v;
  }
  return out;
}

// o jogo hoje só tem "a zubat" como descrição; um texto de verdade aparece quando o jogo puser
function usefulDescription(v: unknown, name: unknown): string | null {
  if (typeof v !== "string") return null;
  const t = v.trim();
  const trivial = typeof name === "string" && t.toLowerCase().replace(/^an? /, "") === name.toLowerCase();
  return t && !trivial ? t : null;
}

export const RARITY_PT: Record<string, string> = {
  COMMON: "Comum", UNCOMMON: "Incomum", RARE: "Rara", EPIC: "Épica", LEGENDARY: "Lendária", MYTHIC: "Mítica",
};

const COLS = "species_id, name, type1, type2, rarity, evolves_to, evolve_level, hunt_level, data";

function toInfo(row: Obj): Omit<SpeciesInfo, "parents" | "evolves_to_name"> {
  const d = (row.data && typeof row.data === "object" ? row.data : {}) as Obj;
  return {
    species_id: Number(row.species_id),
    name: (row.name as string) ?? null,
    type1: (row.type1 as string) ?? null,
    type2: (row.type2 as string) ?? null,
    rarity: (row.rarity as string) ?? null,
    evolves_to: num(row.evolves_to),
    evolve_level: num(row.evolve_level),
    hunt_level: num(row.hunt_level),
    looktype: num(d.looktype),
    base: baseOf(d),
    attacks: Array.isArray(d.attacks) ? (d.attacks as Attack[]).filter((a) => a && typeof a.name === "string") : [],
    description: usefulDescription(d.description, row.name),
    experience: num(d.experience),
    price_npc: num(d.priceNpc),
  };
}

/** A espécie, quem evolui para ela e para quem ela evolui (só o necessário para a ficha). */
export async function loadSpeciesInfo(sb: SupabaseClient, id: number): Promise<SpeciesInfo | null> {
  const [self, parents] = await Promise.all([
    sb.from("game_species").select(COLS).eq("species_id", id).maybeSingle(),
    sb.from("game_species").select(COLS).eq("evolves_to", id),
  ]);
  if (self.error) throw new Error(self.error.message);
  if (!self.data) return null;
  const info = toInfo(self.data as Obj);
  let next: string | null = null;
  if (info.evolves_to != null) {
    const r = await sb.from("game_species").select("name").eq("species_id", info.evolves_to).maybeSingle();
    next = (r.data?.name as string) ?? null;
  }
  return {
    ...info,
    parents: ((parents.data ?? []) as Obj[]).map((p) => ({ species_id: Number(p.species_id), name: (p.name as string) ?? null })),
    evolves_to_name: next,
  };
}

/** A cadeia de pré-evoluções com os stats base (para o piso da nota de formas evoluídas). */
export async function loadAncestors(sb: SupabaseClient, id: number): Promise<Record<Stat, number>[]> {
  const out: Record<Stat, number>[] = [];
  let cur = id;
  for (let i = 0; i < 4; i++) {
    const { data } = await sb.from("game_species").select(COLS).eq("evolves_to", cur).order("species_id").limit(1);
    const row = (data ?? [])[0] as Obj | undefined;
    if (!row) break;
    const info = toInfo(row);
    if (!info.base) break;
    out.push(info.base);
    cur = info.species_id;
  }
  return out; // do pai para trás
}

// --- regras --------------------------------------------------------------------------------------

export type NotaBand = { id: string; ate: number };
export type GameRules = {
  types: Record<string, Record<string, number>>; // atacante -> defensor -> multiplicador
  bands: NotaBand[]; // FAIXAS_NOTA (vazio enquanto o worker não sincronizou nota-pokemon.mjs)
  evoGain: number | null; // GANHO_MIN_EVOLUCAO
  legendaryMult: number | null;
};

/** Faixas e constantes lidas do `nota-pokemon.mjs`; sem o arquivo ou num formato novo, vazio. */
export function parseNotaModule(src: string | null): Pick<GameRules, "bands" | "evoGain" | "legendaryMult"> {
  if (!src) return { bands: [], evoGain: null, legendaryMult: null };
  const bands: NotaBand[] = [];
  const block = /FAIXAS_NOTA\s*=\s*(?:Object\.freeze\()?\[([\s\S]*?)\]/.exec(src)?.[1] ?? "";
  for (const m of block.matchAll(/id\s*:\s*['"]([\w-]+)['"][^}]*?ate\s*:\s*([\d.]+)/g)) bands.push({ id: m[1], ate: Number(m[2]) });
  if (bands.length === 0) for (const m of block.matchAll(/ate\s*:\s*([\d.]+)[^}]*?id\s*:\s*['"]([\w-]+)['"]/g)) bands.push({ id: m[2], ate: Number(m[1]) });
  const g = /GANHO_MIN_EVOLUCAO\s*=\s*([\d.]+)/.exec(src);
  const l = /MULT_LENDARIO_STATS\s*=\s*([\d.]+)/.exec(src);
  return { bands: bands.sort((a, b) => a.ate - b.ate), evoGain: g ? Number(g[1]) : null, legendaryMult: l ? Number(l[1]) : null };
}

export async function loadGameRules(sb: SupabaseClient): Promise<GameRules> {
  const [regras, nota] = await Promise.all([
    sb.from("game_catalog").select("data").eq("key", "regras").maybeSingle(),
    sb.from("game_files").select("content").eq("path", "shared/nota-pokemon.mjs").maybeSingle(),
  ]);
  const types = ((regras.data?.data as Obj | undefined)?.tabelaTipos ?? {}) as GameRules["types"];
  return { types, ...parseNotaModule((nota.data?.content as string) ?? null) };
}

// --- tipos (shared/tipo-efetividade.mjs) ---------------------------------------------------------

export const TYPES = ["NORMAL", "FIRE", "WATER", "ELECTRIC", "GRASS", "ICE", "FIGHTING", "POISON", "GROUND", "FLYING", "PSYCHIC", "BUG", "ROCK", "GHOST", "DRAGON", "DARK", "STEEL", "FAIRY"];
export const TYPE_PT: Record<string, string> = {
  NORMAL: "Normal", FIRE: "Fogo", WATER: "Água", ELECTRIC: "Elétrico", GRASS: "Planta", ICE: "Gelo", FIGHTING: "Lutador",
  POISON: "Venenoso", GROUND: "Terra", FLYING: "Voador", PSYCHIC: "Psíquico", BUG: "Inseto", ROCK: "Pedra", GHOST: "Fantasma",
  DRAGON: "Dragão", DARK: "Sombrio", STEEL: "Aço", FAIRY: "Fada",
};
// a diagonal da tabela (golpe do mesmo tipo do defensor), igual a DIAGONAL_DE_TIPOS do jogo
const DIAGONAL: Record<string, number> = { FIRE: 0.5, WATER: 0.5, ELECTRIC: 0.5, GRASS: 0.5, ICE: 0.5, POISON: 0.5, PSYCHIC: 0.5, DARK: 0.5, STEEL: 0.5, GHOST: 2, DRAGON: 2 };

function vs(table: GameRules["types"], atk: string, def: string): number {
  const a = atk.toUpperCase(), d = def.toUpperCase();
  if (a === d) return DIAGONAL[a] ?? 1;
  return table[a]?.[d] ?? 1;
}

export function effectiveness(table: GameRules["types"], atk: string, def1: string, def2?: string | null): number {
  let v = vs(table, atk, def1);
  if (def2 && def2 !== def1) v *= vs(table, atk, def2);
  return v;
}

export type Matchups = {
  weak: [string, number][]; // tipos que batem ×2 ou ×4 nele
  resist: [string, number][]; // ×0,5 ou ×0,25
  immune: string[]; // ×0
  strong: string[]; // tipos em que os tipos dele batem ×2
  feeble: [string, number][]; // tipos em que os tipos dele batem ×0,5 ou ×0 (o melhor dos dois)
};

export function matchups(table: GameRules["types"], t1: string | null, t2: string | null): Matchups | null {
  if (!t1 || Object.keys(table).length === 0) return null;
  const out: Matchups = { weak: [], resist: [], immune: [], strong: [], feeble: [] };
  const own = [t1, t2].filter((t): t is string => !!t);
  for (const atk of TYPES) {
    const m = effectiveness(table, atk, t1, t2);
    if (m === 0) out.immune.push(atk);
    else if (m > 1) out.weak.push([atk, m]);
    else if (m < 1) out.resist.push([atk, m]);
  }
  for (const def of TYPES) {
    const best = Math.max(...own.map((a) => vs(table, a, def)));
    if (best >= 2) out.strong.push(def);
    else if (best < 1) out.feeble.push([def, best]);
  }
  out.weak.sort((a, b) => b[1] - a[1]);
  out.resist.sort((a, b) => a[1] - b[1]);
  return out;
}

// --- alcance no PvP (shared/pvp-tabuleiro.mjs) ---------------------------------------------------
// folga = SP.ATK − o maior entre ATK e HP. ≤ 0 → corpo a corpo (1); 1–24 → 2 casas; 25–49 → 3; 50+ → 4.

export const RANGE_CUT_3 = 25;
export const RANGE_CUT_4 = 50;

export function pvpRange(base: Record<Stat, number> | null): { range: number; slack: number } | null {
  if (!base) return null;
  const slack = base.spAtk - Math.max(base.atk, base.hp);
  const range = slack <= 0 ? 1 : slack < RANGE_CUT_3 ? 2 : slack < RANGE_CUT_4 ? 3 : 4;
  return { range, slack };
}

export const rangeLabel = (r: number) => (r > 1 ? `${r}🏹` : "🗡️");

// --- nota (shared/nota-pokemon.mjs) --------------------------------------------------------------
// Porte de worker/src/pokeidle_farm/model/capture.py (pokemon_grade), conferido contra o jogo:
// a força de nascimento numa escala logarítmica entre o pior e o melhor nascimento da espécie
// (IV 32, qualidade 1,8, P5, shiny). Não depende do nível.

const QUALITY_EXP: Record<Stat, number> = { hp: 0.95, speed: 0.95, atk: 0.8, def: 0.8, spAtk: 0.8, spDef: 0.8 };
const POTENCY_BONUS = [0, 0.05, 0.1, 0.25, 1];
const REF_BASE = Object.fromEntries(STATS.map((s) => [s, 80])) as Record<Stat, number>;
const allIv = (v: number) => Object.fromEntries(STATS.map((s) => [s, v])) as Record<Stat, number>;

export type Birth = { ivs: Partial<Record<Stat, number>>; quality: number; potency: number; shiny: boolean };

function birthSum(b: Birth, base: Record<Stat, number>): number {
  const q = Math.min(Math.max(b.quality, 0.8), 1.8);
  const m = (1 + POTENCY_BONUS[Math.min(Math.max(b.potency, 1), 5) - 1]) * (b.shiny ? 3 : 1);
  return STATS.reduce((s, k) => s + Math.round((base[k] + 2 * (b.ivs[k] ?? 1)) * q ** QUALITY_EXP[k] * m), 0);
}

const WORST: Birth = { ivs: allIv(1), quality: 0.8, potency: 1, shiny: false };
const BEST: Birth = { ivs: allIv(32), quality: 1.8, potency: 5, shiny: true };
const REF_LO = Math.max(1, birthSum(WORST, REF_BASE));
const REF_HI = Math.max(REF_LO + 1, birthSum(BEST, REF_BASE));

function score(b: Birth, base: Record<Stat, number>): number {
  const s = Math.min(Math.max(birthSum(b, base), REF_LO), REF_HI);
  const raw = (10 * (Math.log(Math.max(1, s)) - Math.log(REF_LO))) / (Math.log(REF_HI) - Math.log(REF_LO));
  return Math.min(Math.max(Math.round(Math.min(Math.max(raw, 0), 10) * 1000) / 1000 / 10, 0), 1);
}

export function grade(b: Birth, base: Record<Stat, number>): number {
  const mn = score(WORST, base);
  const mx = Math.max(mn, score(BEST, base));
  if (mx <= mn) return 0;
  const s = Math.min(Math.max(score(b, base), mn), mx);
  return Math.round(((10 * (s - mn)) / (mx - mn)) * 1000) / 1000;
}

/** Com o piso da linhagem: evoluir sempre sobe a nota pelo menos `gain` por evolução (teto 10). */
export function gradeWithLineage(b: Birth, base: Record<Stat, number>, ancestors: Record<Stat, number>[], gain: number | null): number {
  let g = grade(b, base);
  if (gain != null && ancestors.length) {
    // ancestors[0] é o pai; o piso é a nota do pai (com o piso dele) + gain
    const parent = gradeWithLineage(b, ancestors[0], ancestors.slice(1), gain);
    g = Math.max(g, Math.min(10, parent + gain));
  }
  return g;
}

export function bandOf(bands: NotaBand[], g: number): NotaBand | null {
  return bands.find((b) => g <= b.ate) ?? bands[bands.length - 1] ?? null;
}

export const BAND_PT: Record<string, string> = {
  "extremamente-fraco": "Extremamente fraco", fraco: "Fraco", mediano: "Mediano", razoavel: "Razoável", bom: "Bom",
  forte: "Forte", poderoso: "Poderoso", mitico: "Mítico", legendario: "Lendário", divino: "Divino",
};

export const isLegendary = (rarity: string | null) => !!rarity && /LEND|LEGEND|MYTH|MITIC/i.test(rarity);

// --- selos coloridos (os degraus t1–t5 do jogo: app.js e nota-pokemon.mjs) -----------------------

const QUALITY_BANDS = [ // BANDAS_QUALIDADE: chance (%) de cada faixa de qualidade no nascimento
  [0.8, 0.9, 5], [0.9, 1.0, 5], [1.0, 1.1, 34.03846], [1.1, 1.2, 20], [1.2, 1.3, 10], [1.3, 1.4, 10],
  [1.4, 1.5, 10], [1.5, 1.6, 5], [1.7, 1.8, 0.67308], [1.8, 1.8, 0.28846],
] as const;
const CUTS_IV = [0.5, 0.7, 0.85, 0.95];
const CUTS_QUALITY = [0.44, 0.74, 0.94, 0.99];
const CUTS_GRADE = [3.5, 5.5, 7, 8.5];
const IV_SUM_MIN = 6, IV_SUM_MAX = 192;
const byCuts = (v: number, cuts: number[]) => cuts.reduce((n, c) => (v >= c ? n + 1 : n), 1);

/** Percentil da qualidade entre os nascimentos (percentilQualidade do jogo). */
export function qualityPercentile(q: number): number {
  const v = Math.min(1.8, Math.max(0.8, q));
  let acc = 0;
  for (const [min, max, chance] of QUALITY_BANDS) {
    if (v < min) break;
    if (v >= max) { acc += chance; continue; }
    acc += chance * ((v - min) / (max - min));
    break;
  }
  return Math.min(1, Math.max(0, acc / 100));
}

export const tierPotency = (p: number) => Math.min(5, Math.max(1, Math.round(p)));
export const tierQuality = (q: number) => byCuts(qualityPercentile(q), CUTS_QUALITY);
export const tierIvSum = (s: number) => byCuts((s - IV_SUM_MIN) / (IV_SUM_MAX - IV_SUM_MIN), CUTS_IV);
export const tierGrade = (n: number) => byCuts(n, CUTS_GRADE);
/** IV de um stat (classeIvStat): ≤5, ≤10, ≤15, ≤24, 25+. */
export const tierIvStat = (v: number) => (v <= 5 ? 1 : v <= 10 ? 2 : v <= 15 ? 3 : v <= 24 ? 4 : 5);
