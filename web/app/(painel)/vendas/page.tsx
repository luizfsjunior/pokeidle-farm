import { ItemIcon } from "@/components/ItemIcon";
import { AccountTabs, ErrorNote, Explain, Kpi, PageHeader, Panel } from "@/components/Page";
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
  // último ciclo do seller com decisões, por conta
  const plans = new Map<string, MarketEvent>();
  for (const e of events) {
    if (e.type === "seller.plan" && Array.isArray(e.data?.stones) && !plans.has(e.account_id)) plans.set(e.account_id, e);
  }
  const activity: Activity[] = events
    .filter((e) => (e.type.startsWith("seller.") && e.type !== "seller.plan") || e.type.startsWith("action."))
    .filter((e) => !(e.type === "action.sent" && e.data?.action === "market.meus")) // a leitura de cada ciclo
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
      <PageHeader
        title="Vendas"
        subtitle={<>Anúncios no Mercado nos últimos {DAYS} dias{lastMine ? `; a lista do jogo chegou ${ago(lastMine.received_at)}` : ""}.</>}
      >
        <AccountTabs accounts={accounts} chosen={chosen?.id ?? null} href={(id) => (id ? `/vendas?conta=${id}` : "/vendas")} />
      </PageHeader>
      <ErrorNote message={err} />

      <div className="stack">
        <div className="kpis">
          <Kpi label="Anúncios abertos" value={num(open.length)} note={`${num(open.reduce((s, l) => s + l.qty, 0))} unidades`} />
          <Kpi label="Gemas anunciadas" value={num(openGems)} tone="gem" />
          <Kpi label="Unidades vendidas" value={num(sold.reduce((s, l) => s + l.soldQty, 0))} />
          <Kpi label="Gemas recebidas" value={num(soldGems * (1 - MARKET_FEE))} tone="gem" note={`já sem os ${MARKET_FEE * 100}% de taxa`} />
        </div>
        {sellers.map((s) => (
          <p key={s.account_id} className={`status-line ${s.enabled && s.config?.dry_run === false ? "is-on" : ""}`}>
            <span className="status-dot" aria-hidden />
            <span><strong>{nicks.get(s.account_id)}</strong>: seller {s.enabled ? "ligado" : "desligado"}
            {s.enabled && s.config?.dry_run !== false && ", em simulação: só registra o que faria, sem anunciar"}</span>
          </p>
        ))}

        {[...plans.values()].map((p) => (
          <Panel key={p.account_id} title={<>Decisão do seller{!chosen && <> em {nicks.get(p.account_id)}</>}</>}
            meta={`último ciclo ${ago(p.received_at)}`} flush>
            <StoneTable stones={p.data?.stones as Stone[]} />
            <p className="panel-note">
              Só anuncia se a fila à frente mais o lote vende em até{" "}
              {num(Number(sellers.find((s) => s.account_id === p.account_id)?.config?.max_days ?? 3))} dias, pelo volume
              vendido na semana. O piso ({num(Number(sellers.find((s) => s.account_id === p.account_id)?.config?.floor_ratio ?? 0.85) * 100)}%)
              é da menor entre a média do jogo e a mediana das vendas.
            </p>
          </Panel>
        ))}

        <div className="cols-2">
          <Panel title="Abertos" meta={num(open.length)} flush>
            {open.length === 0
              ? <p className="panel-empty">Nenhum anúncio aberto na última lista do jogo.</p>
              : <ListingTable rows={open} label={label} icon={icon} nicks={chosen ? null : nicks} open />}
          </Panel>

          <Panel title="Vendidos e cancelados" meta={num(closed.length)} flush>
            {closed.length === 0
              ? <p className="panel-empty">Nada vendido ou cancelado no período.</p>
              : <ListingTable rows={closed} label={label} icon={icon} nicks={chosen ? null : nicks} />}
            <p className="panel-note">
              &quot;Saiu da lista&quot; é um anúncio que sumiu sem o worker ter cancelado: quase sempre venda, mas pode ter
              sido cancelado no navegador.
            </p>
          </Panel>
        </div>

        {notices.length > 0 && (
          <Panel title="Avisos do jogo">
            <ul className="activity">
              {notices.map((e, i) => (
                <li key={i}>
                  <span className="muted num">{dateTime(e.received_at)}</span>
                  <span><strong>{String(e.data?.t)}</strong> {noticeSummary(e.raw)}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel title="O que o worker fez" meta="últimas 60 ações">
          {activity.length === 0 ? (
            <p className="muted small" style={{ margin: 0 }}>Nenhuma ação de Mercado no período.</p>
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
        </Panel>

        <Explain title="Diagnóstico: respostas do Mercado recebidas">
          <p>Respostas <code>market</code> por aba, nos últimos {DAYS} dias (até as 500 mais recentes).
            A página usa as abas <code>meus</code> e <code>criado</code>.</p>
          <ul className="small">
            {[...abaCount].map(([k, n]) => <li key={k}><code>{k}</code>: {num(n)}</li>)}
            {abaCount.size === 0 && <li className="muted">nenhuma</li>}
          </ul>
        </Explain>
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
    <div className="table-scroll">
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

type Stone = {
  item_id: number; name: string; stock: number; listed: number; avg: number | null; median?: number | null;
  sales?: number; ref?: number | null; ref_source?: "median" | "avg"; min_ask: number | null;
  target?: number; floor?: number; decision?: string;
  ahead?: number; per_day?: number; days_to_sell?: number | null; floor_reason?: string;
};

const DECISION_LABEL: Record<string, string> = {
  guarda_fila_longa: "Guarda: a fila não anda (passa do limite de dias)",
  guarda_abaixo_do_piso: "Guarda: o mercado está abaixo do piso",
  sem_media: "Guarda: sem preço de referência",
  sem_leitura_de_anuncios: "Espera: sem leitura recente dos anúncios",
  anunciado: "Anuncia",
  reprecificado: "Reprecifica",
  lote_novo: "Anuncia um lote novo",
  limite_de_anuncios: "Guarda: limite de 20 anúncios",
  ok: "Nada a fazer",
};

function StoneTable({ stones }: { stones: Stone[] }) {
  if (stones.length === 0) return <p className="muted small">Nenhuma pedra acima da reserva.</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Pedra</th><th className="r">Estoque</th><th className="r">Anunciado</th><th className="r">Média do jogo</th>
            <th className="r">Mediana das vendas</th><th className="r">Menor anúncio</th><th className="r">Fila à frente</th>
            <th className="r">Vendas/dia</th><th className="r">Dias p/ vender</th><th className="r">Alvo</th>
            <th className="r">Piso</th><th>Decisão</th>
          </tr>
        </thead>
        <tbody>
          {stones.map((s) => (
            <tr key={s.item_id}>
              <td>{s.name}</td>
              <td className="r">{num(s.stock)}</td>
              <td className="r">{num(s.listed)}</td>
              <td className={`r ${s.ref_source === "avg" ? "" : "muted"}`}>{num(s.avg)}</td>
              <td className={`r ${s.ref_source === "median" ? "" : "muted"}`}>
                {s.median != null ? <>{num(s.median)} <span className="muted small">({num(s.sales ?? 0)})</span></> : "—"}
              </td>
              <td className="r">{num(s.min_ask)}</td>
              <td className="r">{num(s.ahead)}</td>
              <td className="r">{num(s.per_day)}</td>
              <td className="r">{s.days_to_sell === undefined ? "—" : s.days_to_sell === null ? "∞" : num(s.days_to_sell)}</td>
              <td className="r">{num(s.target)}</td>
              <td className="r" title={s.floor_reason === "preco_estabelecido" ? "Mais de um dia de demanda parada no menor preço, e ela anda: o piso desce até ele" : undefined}>
                {num(s.floor)}{s.floor_reason === "preco_estabelecido" && <span className="muted small"> (preço do mercado)</span>}
              </td>
              <td className={s.decision?.startsWith("guarda") ? "muted" : undefined}>{DECISION_LABEL[s.decision ?? ""] ?? s.decision ?? "—"}</td>
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
