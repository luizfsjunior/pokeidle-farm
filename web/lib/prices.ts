import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Preço justo de pokémon no Mercado (docs/design/preco-justo-pokemon.md): vem das vendas reais da mesma espécie,
 * shiny, potência e nível parecido, com mais peso para as recentes e para notas parecidas. Em gemas, brutas
 * (o que o comprador paga); `fair_net` é o que entra depois da comissão.
 */
export type MonPrice = {
  pokemon_id: number;
  fair: number | null;
  quick: number | null;
  patient: number | null;
  fair_net: number | null;
  median: number | null;
  sales: number;
  outliers: number;
  match: "exact" | "band";
  confidence: "ok" | "low";
  top_pct: number | null;
  species_sales: number;
  last_sale_at: string | null;
};

const n = (v: unknown): number | null => (v == null ? null : Number.isFinite(Number(v)) ? Number(v) : null);

export async function loadMonPrices(sb: SupabaseClient, accountId: string): Promise<Map<number, MonPrice>> {
  const { data, error } = await sb.rpc("pokemon_prices", { p_account_id: accountId });
  if (error) throw new Error(error.message);
  const out = new Map<number, MonPrice>();
  for (const r of (data ?? []) as Record<string, unknown>[]) {
    const id = Number(r.pokemon_id);
    out.set(id, {
      pokemon_id: id,
      fair: n(r.fair), quick: n(r.quick), patient: n(r.patient), fair_net: n(r.fair_net), median: n(r.median),
      sales: Number(r.sales ?? 0), outliers: Number(r.outliers ?? 0),
      match: r.match === "exact" ? "exact" : "band",
      confidence: r.confidence === "ok" ? "ok" : "low",
      top_pct: n(r.top_pct), species_sales: Number(r.species_sales ?? 0),
      last_sale_at: typeof r.last_sale_at === "string" ? r.last_sale_at : null,
    });
  }
  return out;
}

/** O preço para ordenar e mostrar: só com referências suficientes. */
export const fairOf = (p: MonPrice | undefined): number | null => (p && p.confidence === "ok" ? p.fair : null);

export type Verdict = "excepcional" | "ótimo" | "bom" | "justo" | "caro" | "poucas referências";
export const VERDICT_CLASS: Record<Verdict, string> = {
  excepcional: "tier-5", ótimo: "tier-4", bom: "tier-3", justo: "tier-2", caro: "tier-1", "poucas referências": "",
};

export type ListingVerdict = {
  listing_id: number;
  seen_at: string;
  name: string | null;
  species_id: number;
  shiny: boolean;
  potency: number | null;
  grade: number | null;
  level: number | null;
  price: number;
  fair: number | null;
  diff_pct: number | null;
  sales: number;
  confidence: "ok" | "low";
  top_pct: number | null;
  verdict: Verdict;
};

export async function loadListingVerdicts(sb: SupabaseClient): Promise<ListingVerdict[]> {
  const { data, error } = await sb.rpc("pokemon_listing_verdicts");
  if (error) throw new Error(error.message);
  return ((data ?? []) as Record<string, unknown>[]).map((r) => ({
    listing_id: Number(r.listing_id),
    seen_at: String(r.seen_at),
    name: typeof r.name === "string" ? r.name : null,
    species_id: Number(r.species_id),
    shiny: !!r.shiny,
    potency: n(r.potency),
    grade: n(r.grade),
    level: n(r.level),
    price: Number(r.price),
    fair: n(r.fair),
    diff_pct: n(r.diff_pct),
    sales: Number(r.sales ?? 0),
    confidence: r.confidence === "ok" ? "ok" : "low",
    top_pct: n(r.top_pct),
    verdict: (r.verdict as Verdict) ?? "poucas referências",
  }));
}
