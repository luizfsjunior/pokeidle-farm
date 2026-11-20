import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Loja do NPC (refatoracao-2026-11-20, seção 5). Os preços dos itens são os do worker
 * (worker/src/pokeidle_farm/catalog.py, ITEM_PRICES); os das bolas vêm do catálogo do jogo (loadGameRules).
 * shortcut: lista copiada do worker; se a loja mudar, atualizar os dois lados.
 */
export const SHOP_ITEMS: { id: number; name: string; price: number; note: string }[] = [
  { id: 200, name: "Small Potion", price: 50, note: "+60 HP" },
  { id: 201, name: "Great Potion", price: 150, note: "+150 HP" },
  { id: 202, name: "Ultra Potion", price: 400, note: "+400 HP" },
  { id: 203, name: "Hyper Potion", price: 800, note: "+1.000 HP" },
  { id: 204, name: "Ultimate Potion", price: 1_500, note: "+3.000 HP" },
  { id: 70070, name: "Golden Potion", price: 2_500, note: "50% do HP" },
  { id: 205, name: "Revive", price: 600, note: "revive com 10% do HP" },
  { id: 206, name: "Max Revive", price: 5_000, note: "revive com 100% do HP" },
  // ovos da chocadeira (shared/chocadeira.mjs do jogo): o pokémon nasce com essa potência
  { id: 70091, name: "Mystery Egg P2", price: 20_000_000, note: "ovo potência 2, choca em 6 h" },
  { id: 70092, name: "Mystery Egg P3", price: 120_000_000, note: "ovo potência 3, choca em 12 h" },
  { id: 70093, name: "Mystery Egg P4", price: 250_000_000, note: "ovo potência 4, choca em 24 h" },
];
export const EGG_IDS = new Set([70091, 70092, 70093]);
/** Acima disso a Loja pede confirmação (um ovo P2 custa 20 M). */
export const CONFIRM_GOLD = 1_000_000;

/** Ouro gasto nas compras automáticas (restock e captura) nas últimas 24 h, por "kind:id". */
export async function loadSpend(sb: SupabaseClient, accountId: string): Promise<Map<string, { qty: number; gold: number }>> {
  const since = new Date(Date.now() - 24 * 3600_000).toISOString();
  // o PostgREST devolve até 1.000 linhas por pedido: pagina (num dia ruim passam de 1.500 compras)
  const rows: { data: unknown }[] = [];
  for (let from = 0; from < 20_000; from += 1000) {
    const { data, error } = await sb.from("events").select("data").eq("account_id", accountId)
      .in("type", ["restock.bought", "capture_target.bought"]).gte("received_at", since)
      .order("received_at", { ascending: false }).range(from, from + 999);
    if (error) throw new Error(error.message);
    rows.push(...(data ?? []));
    if (!data || data.length < 1000) break;
  }
  const out = new Map<string, { qty: number; gold: number }>();
  for (const r of rows) {
    const d = (r.data ?? {}) as { kind?: string; id?: number; ball_id?: number; qty?: number; gold_spent?: number };
    const key = d.ball_id != null ? `ball:${d.ball_id}` : `${d.kind ?? "item"}:${d.id}`;
    const cur = out.get(key) ?? { qty: 0, gold: 0 };
    out.set(key, { qty: cur.qty + (d.qty ?? 0), gold: cur.gold + (d.gold_spent ?? 0) });
  }
  return out;
}

/** Menor anúncio aberto e unidades na fila de cada item (último snapshot do market_asks), em gemas. */
export async function loadAsks(sb: SupabaseClient, itemIds: number[]): Promise<Map<number, { min: number | null; units: number }>> {
  if (itemIds.length === 0) return new Map();
  const since = new Date(Date.now() - 3 * 3600_000).toISOString();
  const { data } = await sb.from("market_asks").select("taken_at, item_id, min_price, total_units")
    .in("item_id", itemIds).eq("currency", "orb").gte("taken_at", since).order("taken_at", { ascending: false });
  const out = new Map<number, { min: number | null; units: number }>();
  for (const r of data ?? []) {
    const id = Number(r.item_id);
    if (!out.has(id)) out.set(id, { min: r.min_price == null ? null : Number(r.min_price), units: Number(r.total_units) });
  }
  return out;
}
