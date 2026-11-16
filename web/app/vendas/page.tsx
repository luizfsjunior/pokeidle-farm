import Link from "next/link";
import { ItemIcon } from "@/components/ItemIcon";
import { Shell } from "@/components/Shell";
import { ago, dateTime, num } from "@/lib/format";
import { buildListings, MARKET_FEE, noticeSummary, STATUS_LABEL, type Listing, type MarketEvent } from "@/lib/sales";
import { itemIconUrl } from "@/lib/sprites";
import { requireUser } from "@/lib/supabase/server";
import type { Account } from "@/lib/types";

export const dynamic = "force-dynamic";

const DAYS = 30;
const MARKET_ACTIONS = new Set(["market.criar", "market.cancelar", "market.meus"]);
const NOTICE_TYPES = new Set(["venda", "marketComprado", "aviso", "mktSorteio"]);

type Activity = { at: string; accountId: string; text: string; tone?: "error" | "muted" };

/** Anúncios das contas no Mercado: abertos, vendidos e cancelados, e o que o seller fez (docs/design/pagina-vendas.md). */
export default async function SalesPage({ searchParams }: { searchParams: Promise<{ conta?: string }> }) {
  const { conta } = await searchParams;
  const { supabase, email } = await requireUser();
  const since = new Date(Date.now() - DAYS * 86400_000).toISOString();

  const accountsRes = await supabase.from("accounts").select("id, nick, role, enabled, status").order("nick");
  const accounts = (accountsRes.data ?? []) as Account[];
  const chosen = accounts.find((a) => a.id === conta) ?? null;
  const nicks = new Map(accounts.map((a) => [a.id, a.nick]));

  // uma consulta por fonte, para nenhuma lotar o limite das outras
  const base = () => {
    const b = supabase.from("events").select("received_at, account_id, type, data, raw").gte("received_at", since);
    return chosen ? b.eq("account_id", chosen.id) : b;
  };
  let abas = supabase.from("events").select("received_at, aba:data->aba").eq("type", "market.reply")
    .gte("received_at", since).order("received_at", { ascending: false }).limit(500);
  if (chosen) abas = abas.eq("account_id", chosen.id);
  const [replies, actions, seller, notes, abasRes, sellerRes] = await Promise.all([
    base().eq("type", "market.reply").in("data->>aba", ["meus", "criado"]).order("received_at", { ascending: false }).limit(1500),
    base().in("type", ["action.sent", "action.blocked", "action.failed"]).in("data->>action", [...MARKET_ACTIONS])
      .order("received_at", { ascending: false }).limit(1000),
    base().like("type", "seller.%").order("received_at", { ascending: false }).limit(300),
    base().eq("type", "unknown").in("data->>t", [...NOTICE_TYPES]).order("received_at", { ascending: false }).limit(200),
    abas,
    supabase.from("strategy_configs").select("account_id, enabled, config").eq("plugin", "seller"),
  ]);
  const evRes = replies.error ? replies : actions.error ? actions : seller.error ? seller : notes;
  const events = ([replies, actions, seller, notes].flatMap((r) => r.data ?? []) as MarketEvent[])
    .sort((a, b) => b.received_at.localeCompare(a.received_at));
  const listings = buildListings(events);

  // nomes e ícones do catálogo
  const itemIds = [...new Set(listings.map((l) => l.itemId).filter((i): i is number => i != null))];
  const itemsRes = itemIds.length
    ? await supabase.from("game_items").select("item_id, name, icon").in("item_id", itemIds)
    : { data: [] };
  const items = new Map(((itemsRes.data ?? []) as { item_id: number; name: string; icon: string | null }[])
    .map((r) => [r.item_id, r]));
  const label = (l: Listing) => l.name ?? (l.itemId != null ? items.get(l.itemId)?.name : null) ?? `Item #${l.itemId ?? "?"}`;
  const icon = (l: Listing) => itemIconUrl(l.itemId != null ? items.get(l.itemId)?.icon : null);

  const open = listings.filter((l) => l.status === "aberto");
  const closed = listings.filter((l) => l.status !== "aberto");
  const sold = listings.filter((l) => l.soldQty > 0);
  const gemsOf = (ls: Listing[], qty: (l: Listing) => number) =>
    ls.filter((l) => l.currency === "orb").reduce((s, l) => s + qty(l) * (l.price ?? 0), 0);
  const openGems = gemsOf(open, (l) => l.qty);
  const soldGems = gemsOf(sold, (l) => l.soldQty);

  const notices = events.filter((e) => e.type === "unknown").slice(0, 30);
  const activity: Activity[] = events
    .filter((e) => e.type.startsWith("seller.") || e.type.startsWith("action."))
    .slice(0, 60)
    .map((e) => ({ at: e.received_at, accountId: e.account_id, ...describe(e) }));

  const abaCount = new Map<string, number>();
  for (const r of (abasRes.data ?? []) as { aba: unknown }[]) {
    const k = r.aba == null ? "(sem aba)" : String(r.aba);
    abaCount.set(k, (abaCount.get(k) ?? 0) + 1);
  }
  const lastMine = events.find((e) => e.type === "market.reply" && e.data?.aba === "meus");
  const sellers = ((sellerRes.data ?? []) as { account_id: string; enabled: boolean; config: Record<string, unknown> }[])
    .filter((s) => !chosen || s.account_id === chosen.id);
  const err = accountsRes.error?.message ?? evRes.error?.message;

  return (
    <Shell email={email}>
      <h1>Vendas</h1>
      <p className="secondary small">
        Anúncios no Mercado nos últimos {DAYS} dias{chosen ? ` de ${chosen.nick}` : ", todas as contas"}. A lista vem do
        próprio jogo: o seller pede os anúncios a cada ciclo{lastMine ? `; a última chegou ${ago(lastMine.received_at)}` : ""}.
      </p>
      <p className="small">
        {[null, ...accounts].map((a) => (
          <span key={a?.id ?? "todas"} style={{ marginRight: ".75rem" }}>
            {(a?.id ?? null) === (chosen?.id ?? null)
              ? <strong>{a?.nick ?? "Todas"}</strong>
              : <Link href={a ? `/vendas?conta=${a.id}` : "/vendas"}>{a?.nick ?? "Todas"}</Link>}
          </span>
        ))}
      </p>
      {err && <p className="error">Erro ao ler o Supabase: {err}</p>}

      <div className="stack">
        <section className="card">
          <div className="sales-totals">
            <Total value={num(open.length)} label="anúncios abertos" />
            <Total value={num(open.reduce((s, l) => s + l.qty, 0))} label="unidades à venda" />
            <Total value={num(openGems)} label="gemas anunciadas" tone="gem" />
            <Total value={num(sold.reduce((s, l) => s + l.soldQty, 0))} label="unidades vendidas" />
            <Total value={num(soldGems * (1 - MARKET_FEE))} label={`gemas recebidas (− ${MARKET_FEE * 100}% de taxa)`} tone="gem" />
          </div>
          {sellers.map((s) => (
            <p key={s.account_id} className="small secondary" style={{ margin: ".75rem 0 0" }}>
              {nicks.get(s.account_id)}: seller {s.enabled ? "ligado" : "desligado"}
              {s.enabled && s.config?.dry_run !== false && ", em simulação (dry_run): ele só registra o que faria, sem anunciar"}
            </p>
          ))}
        </section>

        <section className="card">
          <h2>Abertos</h2>
          {open.length === 0
            ? <p className="muted small">Nenhum anúncio aberto na última lista do jogo.</p>
            : <ListingTable rows={open} label={label} icon={icon} nicks={chosen ? null : nicks} open />}
        </section>

        <section className="card">
          <h2>Vendidos e cancelados</h2>
          <p className="muted small" style={{ marginTop: 0 }}>
            &quot;Saiu da lista&quot; é um anúncio que sumiu sem o worker ter cancelado: quase sempre venda, mas pode ter
            sido cancelado no navegador.
          </p>
          {closed.length === 0
            ? <p className="muted small">Nada vendido ou cancelado no período.</p>
            : <ListingTable rows={closed} label={label} icon={icon} nicks={chosen ? null : nicks} />}
        </section>

        {notices.length > 0 && (
          <section className="card">
            <h2>Avisos do jogo</h2>
            <ul className="activity">
              {notices.map((e, i) => (
                <li key={i}>
                  <span className="muted num">{dateTime(e.received_at)}</span>
                  <span><strong>{String(e.data?.t)}</strong> {noticeSummary(e.raw)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="card">
          <h2>O que o worker fez</h2>
          {activity.length === 0 ? (
            <p className="muted small">Nenhuma ação de Mercado no período.</p>
          ) : (
            <ul className="activity">
              {activity.map((a, i) => (
                <li key={i} className={a.tone}>
                  <span className="muted num">{dateTime(a.at)}</span>
                  <span>{!chosen && <>{nicks.get(a.accountId)}: </>}{a.text}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <details className="card">
          <summary><strong>Diagnóstico: respostas do Mercado recebidas</strong></summary>
          <p className="small secondary">Respostas <code>market</code> por aba, nos últimos {DAYS} dias (até as 500 mais recentes).
            A página usa as abas <code>meus</code> e <code>criado</code>.</p>
          <ul className="small">
            {[...abaCount].map(([k, n]) => <li key={k}><code>{k}</code>: {num(n)}</li>)}
            {abaCount.size === 0 && <li className="muted">nenhuma</li>}
          </ul>
        </details>
      </div>
    </Shell>
  );
}

function ListingTable({ rows, label, icon, nicks, open = false }: {
  rows: Listing[];
  label: (l: Listing) => string;
  icon: (l: Listing) => string | null;
  nicks: Map<string, string> | null;
  open?: boolean;
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Item</th>
            {nicks && <th>Conta</th>}
            <th className="r">Qtd</th>
            {!open && <th className="r">Vendidas</th>}
            <th className="r">Preço</th>
            <th className="r">Total</th>
            <th>{open ? "Anunciado" : "Situação"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => (
            <tr key={l.id}>
              <td>
                <span className="sale-item">
                  <ItemIcon src={icon(l)} name={label(l)} size={24} />
                  {label(l)}
                </span>
              </td>
              {nicks && <td>{nicks.get(l.accountId)}</td>}
              <td className="r">{num(open ? l.qty : l.firstQty)}</td>
              {!open && <td className="r">{num(l.soldQty)}</td>}
              <td className="r">{l.price == null ? "—" : `${num(l.price)} ${l.currency === "orb" ? "gemas" : "ouro"}`}</td>
              <td className="r">{l.price == null ? "—" : num(l.price * (open ? l.qty : l.soldQty || l.firstQty))}</td>
              <td>
                {open ? (
                  <span className="small">{dateTime(l.createdAt)}</span>
                ) : (
                  <span className={`sale-status sale-${l.status.replace("?", "")}`}>
                    {STATUS_LABEL[l.status]}
                    {l.gameState && l.status === "outro" && ` (${l.gameState})`}
                    <span className="muted small"> {dateTime(l.closedAt)}</span>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Total({ value, label, tone }: { value: string; label: string; tone?: "gem" }) {
  return (
    <div className="figure">
      <span className={`figure-value num ${tone === "gem" ? "tone-gem" : ""}`}>{value}</span>
      <span className="figure-label">{label}</span>
    </div>
  );
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
