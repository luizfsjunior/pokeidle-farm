import type { SupabaseClient } from "@supabase/supabase-js";
import { num } from "@/lib/format";
import { buildListings, noticeSummary, type Listing, type MarketEvent } from "@/lib/sales";
import { itemIconUrl } from "@/lib/sprites";

export const DAYS = 30;

export type Activity = { at: string; accountId: string; text: string; tone?: "error" | "muted" };
export type SaleRow = Listing & { label: string; icon: string | null };
export type Stone = {
  item_id: number; name: string; stock: number; listed: number; avg: number | null; median?: number | null;
  sales?: number; ref?: number | null; ref_source?: "median" | "avg"; min_ask: number | null;
  target?: number; floor?: number; decision?: string;
  ahead?: number; per_day?: number; days_to_sell?: number | null; floor_reason?: string;
};
export type SellerCfg = { account_id: string; enabled: boolean; config: Record<string, unknown> };

/** Anúncios das contas no Mercado: abertos, vendidos e cancelados, e o que o seller fez (docs/design/pagina-vendas.md). */
export async function loadSales(supabase: SupabaseClient, conta: string | null) {
  const since = new Date(Date.now() - DAYS * 86400_000).toISOString();
  // as quatro fontes (respostas do Mercado, ações de Mercado, ciclos do seller e avisos de venda) numa função
  // do banco: lida direto pelo PostgREST, o filtro no `data` passava pelo RLS sem usar índice e levava até 8 s
  // (migration 20261127150000_painel_rapido.sql). Cada fonte tem o seu limite lá dentro.
  const [eventsRes, sellerRes] = await Promise.all([
    supabase.rpc("market_sales_events", { p_since: since, p_account: conta }),
    supabase.from("strategy_configs").select("account_id, enabled, config").eq("plugin", "seller"),
  ]);
  // sem os eventos, "nenhum anúncio" seria mentira: o erro sobe e a tela mantém os últimos dados bons
  if (eventsRes.error) throw new Error(eventsRes.error.message);
  const events = ((eventsRes.data ?? []) as MarketEvent[])
    .map((e) => ({ ...e, raw: e.raw ?? null }))
    .sort((a, b) => b.received_at.localeCompare(a.received_at));
  const listings = buildListings(events);

  // nomes e ícones do catálogo
  // o anúncio pode vir só com o nome (sem itemId): aí o ícone sai pelo nome
  type Item = { item_id: number; name: string; icon: string | null };
  const itemIds = [...new Set(listings.map((l) => l.itemId).filter((i): i is number => i != null))];
  const names = [...new Set(listings.filter((l) => l.itemId == null && l.name).map((l) => l.name!))];
  const [byIdRes, byNameRes] = await Promise.all([
    itemIds.length ? supabase.from("game_items").select("item_id, name, icon").in("item_id", itemIds) : Promise.resolve({ data: [] }),
    names.length ? supabase.from("game_items").select("item_id, name, icon").in("name", names) : Promise.resolve({ data: [] }),
  ]);
  const items = new Map(((byIdRes.data ?? []) as Item[]).map((r) => [r.item_id, r]));
  const itemsByName = new Map<string, Item>();
  for (const r of (byNameRes.data ?? []) as Item[]) {
    const cur = itemsByName.get(r.name);
    if (!cur || r.item_id < cur.item_id) itemsByName.set(r.name, r);
  }
  const rows: SaleRow[] = listings.map((l) => {
    const it = l.itemId != null ? items.get(l.itemId) : l.name ? itemsByName.get(l.name) : undefined;
    return { ...l, label: l.name ?? it?.name ?? `Item #${l.itemId ?? "?"}`, icon: itemIconUrl(it?.icon) };
  });

  const notices = events.filter((e) => e.type === "unknown").slice(0, 30)
    .map((e) => ({ at: e.received_at, t: String(e.data?.t), text: noticeSummary(e.raw) }));
  // último ciclo do seller com decisões, por conta
  const plans: { accountId: string; at: string; stones: Stone[] }[] = [];
  for (const e of events) {
    if (e.type === "seller.plan" && Array.isArray(e.data?.stones) && !plans.some((p) => p.accountId === e.account_id)) {
      plans.push({ accountId: e.account_id, at: e.received_at, stones: e.data.stones as Stone[] });
    }
  }
  const activity: Activity[] = events
    .filter((e) => (e.type.startsWith("seller.") && e.type !== "seller.plan") || e.type.startsWith("action."))
    .filter((e) => !(e.type === "action.sent" && e.data?.action === "market.meus")) // a leitura de cada ciclo
    .slice(0, 60)
    .map((e) => ({ at: e.received_at, accountId: e.account_id, ...describe(e) }));

  const lastMine = events.find((e) => e.type === "market.reply" && e.data?.aba === "meus")?.received_at ?? null;
  const sellers = ((sellerRes.data ?? []) as SellerCfg[]).filter((s) => !conta || s.account_id === conta);
  return { rows, notices, plans, activity, lastMine, sellers };
}

function describe(e: MarketEvent): { text: string; tone?: "error" | "muted" } {
  const d = (e.data ?? {}) as Record<string, unknown>;
  const input = (d.input ?? {}) as Record<string, unknown>;
  if (e.type.startsWith("action.")) {
    const what = d.action === "market.criar"
      ? `anunciar ${num(Number(input.qtd))}× item ${input.itemId} a ${num(Number(input.preco))} ${input.moeda === "gold" ? "ouro" : "gemas"}`
      : d.action === "market.cancelar" ? `cancelar o anúncio ${input.id}` : "ler os anúncios";
    if (e.type === "action.sent") return { text: `Mandou ${what}`, tone: d.action === "market.meus" ? "muted" : undefined };
    return { text: `Não mandou ${what}: ${String(d.reason ?? "falhou")}`, tone: "error" };
  }
  if (e.type === "seller.would") return { text: `Simulação: faria ${String(d.action)} (${noticeSummary(input)})` };
  if (e.type === "seller.failed") return { text: `Falhou ${String(d.action)}: ${String(d.reason)}`, tone: "error" };
  if (e.type === "seller.plan") {
    if (d.skipped) return { text: `Ciclo pulado: ${String(d.skipped)}`, tone: "muted" };
    const stones = Array.isArray(d.stones) ? d.stones.length : null;
    return {
      text: `Ciclo do seller${stones != null ? `: ${stones} pedra(s) acima da reserva` : ""}, ${num(Number(d.listings ?? 0))} anúncio(s) aberto(s)${d.dry_run ? ", em simulação" : ""}`,
      tone: "muted",
    };
  }
  if (e.type === "seller.probe") return { text: `Sonda: ${noticeSummary(d as Record<string, unknown>)}`, tone: "muted" };
  return { text: e.type, tone: "muted" };
}
