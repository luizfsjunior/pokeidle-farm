import type { SupabaseClient } from "@supabase/supabase-js";
import { gemPrice, STONE_CATEGORY } from "@/lib/money";
import { itemIconUrl } from "@/lib/sprites";

export const DAYS = 7;

type Price = { avg: number; units: number | null };
type Ref = { median: number; sales: number; rawMean: number | null };
export type Row = {
  ref: Ref | null;
  ask: { min: number | null; queue: number } | null;
  name: string;
  qty: number;
  itemId: number | null;
  icon: string | null;
  orb: Price | null;
  gold: Price | null;
  npc: number | null;
  stone: boolean; // pedra: não é fonte de gemas, fica fora do total (docs/design/painel-ux-v2.md)
};

export const goldOf = (r: Row) => (r.gold ? r.gold.avg : r.npc ?? 0);
/** Preço de hoje em gemas (lib/money: a mesma regra de todas as telas). */
export const orbOf = (r: Row) =>
  gemPrice({ median: r.ref?.median, sales: r.ref?.sales, avg: r.orb?.avg, minAsk: r.ask?.min }) ?? 0;

/**
 * Itens que as contas dropam e quanto valem no Mercado (docs/design/fase-7-precos-do-mercado.md, seção 6).
 * Os preços aqui são os do último snapshot; as métricas usam o preço da hora de cada drop.
 */
export async function loadMarket(supabase: SupabaseClient, conta: string | null) {
  const since = new Date(Date.now() - DAYS * 86400_000).toISOString();
  // drops somados por item: abates por minuto (kill_minute) + os do worker antigo ainda em events
  // (docs/design/retencao-eventos.md, "Abates por minuto")
  const [dropsRes, lastSnap, refRes] = await Promise.all([
    supabase.rpc("dropped_items", { p_since: since, p_account: conta }),
    supabase.from("market_prices").select("taken_at").order("taken_at", { ascending: false }).limit(1).maybeSingle(),
    supabase.rpc("market_reference"),
  ]);
  // sem os abates, "nenhum drop" seria mentira: o erro sobe e a tela mantém os últimos dados bons
  if (dropsRes.error) throw new Error(dropsRes.error.message);
  // mediana das vendas reais (docs/design/preco-de-referencia.md); só vale com MIN_SALES vendas
  const refs = new Map<string, Ref>();
  for (const r of (refRes.data ?? []) as { item_name: string; currency: string; median_unit: number; sales: number; raw_mean_unit: number | null }[]) {
    if (r.currency === "orb" && r.median_unit != null) {
      refs.set(r.item_name, { median: Number(r.median_unit), sales: r.sales, rawMean: r.raw_mean_unit == null ? null : Number(r.raw_mean_unit) });
    }
  }

  const byName = new Map<string, number>();
  for (const d of (dropsRes.data ?? []) as { name: string; qty: number }[]) {
    byName.set(d.name, Number(d.qty) || 0);
  }
  const names = [...byName.keys()];
  const takenAt = (lastSnap.data?.taken_at as string | undefined) ?? null;

  const itemsRes = names.length
    ? await supabase.from("game_items").select("item_id, name, npc_price, icon, category").in("name", names)
    : { data: [] };
  type It = { item_id: number; name: string; npc_price: number | null; icon: string | null; category: string | null };
  const itemByName = new Map<string, It>();
  for (const it of (itemsRes.data ?? []) as It[]) {
    const cur = itemByName.get(it.name);
    if (!cur || it.item_id < cur.item_id) itemByName.set(it.name, it);
  }
  const ids = [...itemByName.values()].map((i) => i.item_id);
  const [pricesRes, asksRes] = await Promise.all([
    takenAt && ids.length
      ? supabase.from("market_prices").select("item_id, currency, avg, units").eq("taken_at", takenAt).in("item_id", ids)
      : Promise.resolve({ data: [] }),
    ids.length
      ? supabase.from("market_asks").select("item_id, min_price, total_units").eq("currency", "orb")
          .in("item_id", ids).gte("taken_at", new Date(Date.now() - 6 * 3600_000).toISOString())
          .order("taken_at", { ascending: false }).limit(500)
      : Promise.resolve({ data: [] }),
  ]);
  const asks = new Map<number, { min: number | null; queue: number }>();
  for (const a of (asksRes.data ?? []) as { item_id: number; min_price: number | null; total_units: number }[]) {
    if (!asks.has(a.item_id)) asks.set(a.item_id, { min: a.min_price == null ? null : Number(a.min_price), queue: Number(a.total_units) || 0 });
  }
  const prices = new Map<string, Price>();
  for (const p of (pricesRes.data ?? []) as { item_id: number; currency: string; avg: number; units: number | null }[]) {
    prices.set(`${p.item_id}:${p.currency}`, { avg: Number(p.avg), units: p.units == null ? null : Number(p.units) });
  }

  const rows: Row[] = names.map((name) => {
    const it = itemByName.get(name) ?? null;
    return {
      name,
      ref: refs.get(name) ?? null,
      qty: byName.get(name) ?? 0,
      itemId: it?.item_id ?? null,
      icon: itemIconUrl(it?.icon),
      ask: it ? asks.get(it.item_id) ?? null : null,
      orb: it ? prices.get(`${it.item_id}:orb`) ?? null : null,
      gold: it ? prices.get(`${it.item_id}:gold`) ?? null : null,
      npc: it?.npc_price ?? null,
      stone: it?.category === STONE_CATEGORY,
    };
  });
  // o que rende gemas primeiro (as pedras vão para o fim), do mais valioso ao menos
  rows.sort((a, b) => Number(a.stone) - Number(b.stone) || orbOf(b) * b.qty - orbOf(a) * a.qty || goldOf(b) * b.qty - goldOf(a) * a.qty);
  return { rows, takenAt };
}
