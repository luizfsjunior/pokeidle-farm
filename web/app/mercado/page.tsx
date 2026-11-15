import Link from "next/link";
import { Shell } from "@/components/Shell";
import { dateTime, num } from "@/lib/format";
import { requireUser } from "@/lib/supabase/server";
import type { Account } from "@/lib/types";

export const dynamic = "force-dynamic";

const DAYS = 7;
const MAX_KILLS = 5000; // abates com drop lidos por vez (bem acima do que uma conta faz em 7 dias)

type Price = { avg: number; units: number | null };
type Row = {
  ask: { min: number | null; queue: number } | null;
  name: string;
  qty: number;
  itemId: number | null;
  orb: Price | null;
  gold: Price | null;
  npc: number | null;
};

/**
 * Itens que as contas dropam e quanto valem no Mercado (docs/design/fase-7-precos-do-mercado.md, seção 6).
 * Os preços aqui são os do último snapshot; as métricas usam o preço da hora de cada drop.
 */
export default async function MarketPage({ searchParams }: { searchParams: Promise<{ conta?: string }> }) {
  const { conta } = await searchParams;
  const { supabase, email } = await requireUser();
  const since = new Date(Date.now() - DAYS * 86400_000).toISOString();

  const accountsRes = await supabase.from("accounts").select("id, nick, role, enabled, status").order("nick");
  const accounts = (accountsRes.data ?? []) as Account[];
  const chosen = accounts.find((a) => a.id === conta) ?? null;

  let kills = supabase.from("events").select("data->drops").eq("type", "kill")
    .gte("received_at", since).neq("data->drops", "[]").limit(MAX_KILLS);
  if (chosen) kills = kills.eq("account_id", chosen.id);
  const [killsRes, lastSnap] = await Promise.all([
    kills,
    supabase.from("market_prices").select("taken_at").order("taken_at", { ascending: false }).limit(1).maybeSingle(),
  ]);

  // soma por nome
  const byName = new Map<string, number>();
  for (const k of (killsRes.data ?? []) as { drops: { name?: string; qty?: number }[] | null }[]) {
    for (const d of k.drops ?? []) {
      if (!d?.name) continue;
      byName.set(d.name, (byName.get(d.name) ?? 0) + (Number(d.qty) || 1));
    }
  }
  const names = [...byName.keys()];
  const takenAt = (lastSnap.data?.taken_at as string | undefined) ?? null;

  const itemsRes = names.length
    ? await supabase.from("game_items").select("item_id, name, npc_price").in("name", names)
    : { data: [] as { item_id: number; name: string; npc_price: number | null }[] };
  const itemByName = new Map<string, { item_id: number; npc_price: number | null }>();
  for (const it of (itemsRes.data ?? []) as { item_id: number; name: string; npc_price: number | null }[]) {
    const cur = itemByName.get(it.name);
    if (!cur || it.item_id < cur.item_id) itemByName.set(it.name, it);
  }
  const ids = [...itemByName.values()].map((i) => i.item_id);
  const pricesRes = takenAt && ids.length
    ? await supabase.from("market_prices").select("item_id, currency, avg, units").eq("taken_at", takenAt).in("item_id", ids)
    : { data: [] as { item_id: number; currency: string; avg: number; units: number | null }[] };
  const asksRes = ids.length
    ? await supabase.from("market_asks").select("item_id, min_price, total_units").eq("currency", "orb")
        .in("item_id", ids).gte("taken_at", new Date(Date.now() - 6 * 3600_000).toISOString())
        .order("taken_at", { ascending: false }).limit(500)
    : { data: [] as { item_id: number; min_price: number | null; total_units: number }[] };
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
      qty: byName.get(name) ?? 0,
      itemId: it?.item_id ?? null,
      ask: it ? asks.get(it.item_id) ?? null : null,
      orb: it ? prices.get(`${it.item_id}:orb`) ?? null : null,
      gold: it ? prices.get(`${it.item_id}:gold`) ?? null : null,
      npc: it?.npc_price ?? null,
    };
  });
  const goldOf = (r: Row) => (r.gold ? r.gold.avg : r.npc ?? 0);
  // gemas: o menor entre a média de 7 dias e o menor anúncio aberto (o preço pelo qual vende hoje)
  const orbOf = (r: Row) => (r.orb ? (r.ask?.min != null ? Math.min(r.orb.avg, r.ask.min) : r.orb.avg) : 0);
  // mais valioso primeiro: gemas, depois ouro
  rows.sort((a, b) => orbOf(b) * b.qty - orbOf(a) * a.qty || goldOf(b) * b.qty - goldOf(a) * a.qty);
  const totalOrb = rows.reduce((s, r) => s + r.qty * orbOf(r), 0);
  const totalGold = rows.reduce((s, r) => s + r.qty * goldOf(r), 0);
  const err = accountsRes.error?.message ?? killsRes.error?.message;

  return (
    <Shell email={email}>
      <h1>Mercado</h1>
      <p className="secondary small">
        Drops dos últimos {DAYS} dias{chosen ? ` de ${chosen.nick}` : " de todas as contas"}, valorados pelo preço de venda em
        gemas (o menor entre a média de 7 dias e o menor anúncio aberto) e pela média em ouro do Mercado {takenAt ? `(snapshot de ${dateTime(takenAt)})` : "(ainda sem snapshot de preços)"}. Sem vendas em
        ouro, vale o preço do NPC (marcado com *). As métricas usam o preço da hora de cada drop.
      </p>
      <p className="small">
        {[null, ...accounts].map((a) => (
          <span key={a?.id ?? "todas"} style={{ marginRight: ".75rem" }}>
            {(a?.id ?? null) === (chosen?.id ?? null)
              ? <strong>{a?.nick ?? "Todas"}</strong>
              : <Link href={a ? `/mercado?conta=${a.id}` : "/mercado"}>{a?.nick ?? "Todas"}</Link>}
          </span>
        ))}
      </p>
      {err && <p className="error">Erro ao ler o Supabase: {err}</p>}
      <section className="card">
        <div className="stats">
          <div className="stat"><div className="label">Valor em gemas</div><div className="value">{num(totalOrb)}</div></div>
          <div className="stat"><div className="label">Valor em ouro</div><div className="value">{num(totalGold, { compact: true })}</div></div>
        </div>
      </section>
      {rows.length === 0 ? (
        <p className="muted">Nenhum drop nos últimos {DAYS} dias.</p>
      ) : (
        <div className="card" style={{ overflowX: "auto", marginTop: "1rem" }}>
          <table>
            <thead>
              <tr>
                <th>Item</th><th>Unidades</th><th>Gemas (média)</th><th>Menor anúncio (fila)</th><th>Vendidas</th>
                <th>Ouro (média)</th><th>Vendidas</th><th>Valor (gemas)</th><th>Valor (ouro)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name}>
                  <td>{r.name}{r.itemId === null && <span className="error small"> · fora do catálogo</span>}</td>
                  <td>{num(r.qty)}</td>
                  <td>{r.orb ? num(r.orb.avg) : "—"}</td>
                  <td>{r.ask?.min != null ? `${num(r.ask.min)} (${num(r.ask.queue)})` : "—"}</td>
                  <td className="muted">{r.orb ? num(r.orb.units) : "—"}</td>
                  <td>{r.gold ? num(r.gold.avg, { compact: true }) : r.npc != null ? `${num(r.npc, { compact: true })}*` : "—"}</td>
                  <td className="muted">{r.gold ? num(r.gold.units) : "—"}</td>
                  <td>{num(r.qty * orbOf(r))}</td>
                  <td>{num(r.qty * goldOf(r), { compact: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}
