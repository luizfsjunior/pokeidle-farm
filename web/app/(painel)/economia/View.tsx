"use client";

import { useSearchParams } from "next/navigation";
import { AccountPicker } from "@/components/AccountPicker";
import { ItemIcon } from "@/components/ItemIcon";
import { Ld, LdBlock, LdRows } from "@/components/Loading";
import { Bar, ErrorNote, Fold, Kpi, PageHeader, Panel } from "@/components/Page";
import { ago, dateTime, num } from "@/lib/format";
import { ORB_FEE, usd, USD_PER_ORB } from "@/lib/money";
import { useAccounts, usePanel } from "@/lib/query/hooks";
import { STATUS_LABEL } from "@/lib/sales";
import { loadEvaluation, type EvalRow } from "./evaluation";
import { DAYS as MARKET_DAYS, goldOf, loadMarket, orbOf, type Row } from "./market";
import { DAYS as SALES_DAYS, loadSales, type Activity, type SaleRow, type Stone } from "./sales";
import { SettingsForm } from "./SettingsForm";

/**
 * Economia (docs/design/painel-ux-v2.md): o que as contas rendem em gemas, o que vendem e o que dropam. Juntou
 * as páginas Compensa?, Vendas e Mercado. Pedras não contam como renda.
 */
export function EconomyView() {
  const sp = useSearchParams();
  const accountsQ = useAccounts();
  const accounts = accountsQ.data ?? [];
  const conta = accounts.find((a) => a.id === sp.get("conta"))?.id ?? null;
  const nicks = new Map(accounts.map((a) => [a.id, a.nick]));
  const ready = accountsQ.isSuccess;
  const ev = usePanel(["compensa"], loadEvaluation, { enabled: ready }).data;
  const salesQ = usePanel(["vendas", conta], (sb) => loadSales(sb, conta), { enabled: ready });
  const marketQ = usePanel(["mercado", conta], (sb) => loadMarket(sb, conta), { enabled: ready });
  const sales = salesQ.data;
  const market = marketQ.data;

  return (
    <>
      <PageHeader title="Economia" hint={<>
        <p>Pedras não contam como renda: vendem a 2 gemas com milhares na fila. Elas aparecem nos drops e no seller, mas
          ficam fora do total.</p>
        <p>Preço de hoje: a mediana das vendas reais (ou a média do jogo, com poucas vendas), limitada pelo menor anúncio
          aberto. Renda em US$: gemas × (1 − {num(ORB_FEE * 100)}% de comissão) × US$ {String(USD_PER_ORB).replace(".", ",")}.</p>
      </>}>
        <AccountPicker accounts={accounts} chosen={conta} hasParam={sp.has("conta")}
          href={(id) => (id ? `/economia?conta=${id}` : "/economia")} />
      </PageHeader>
      <ErrorNote message={ev?.err ?? salesQ.error?.message ?? marketQ.error?.message ?? accountsQ.error?.message} />

      <div className="stack">
        <Verdict ev={ev} conta={conta} received={sales ? receivedGems(sales.rows) : null} />
        <SalesBlock d={sales} conta={conta} nicks={nicks} />
        <DropsBlock d={market} />
        {ev && ev.accounts.length > 1 && !conta && <PerAccount rows={ev.accounts} />}
        {ev && <Fold title="Custos do mês" meta={ev.total?.cost_usd != null ? usd(ev.total.cost_usd) : "não informado"}>
          <SettingsForm initial={ev.settings} />
        </Fold>}
      </div>
    </>
  );
}

/** Gemas que o Mercado já pagou (sem a comissão), dos anúncios vendidos. */
function receivedGems(rows: SaleRow[]): number {
  return rows.filter((l) => l.currency === "orb").reduce((s, l) => s + l.soldQty * (l.price ?? 0), 0) * (1 - ORB_FEE);
}

/** Compensa? Lucro do mês projetado pelos drops (sem pedras) contra o custo, e o que já entrou de verdade. */
function Verdict({ ev, conta, received }: { ev: Awaited<ReturnType<typeof loadEvaluation>> | undefined; conta: string | null; received: number | null }) {
  if (!ev) return <LdBlock h={190} />;
  const row = conta ? ev.accounts.find((a) => a.account_id === conta) ?? null : ev.total;
  const days = ev.settings.window_days;
  const enough = (row?.data_days ?? 0) >= days - 0.05;
  const cost = conta ? null : ev.total?.cost_usd ?? null; // o custo é do conjunto, não de uma conta
  const income = row?.income_usd_as_is ?? null;
  const profit = income == null ? null : income - (cost ?? 0);
  const headline = cost == null ? income : profit; // sem o custo (uma conta só), mostra a renda
  const verdict = !row ? "Sem dados ainda" : !enough ? "Ainda medindo" : (profit ?? 0) > 0 ? "Compensa" : "Não compensa";
  const max = Math.max(income ?? 0, cost ?? 0);
  return (
    <section className="card stack verdict">
      <div className="spread">
        <h2 style={{ margin: 0 }}>{verdict}</h2>
        <span className="muted small">{row ? `${num(row.data_days)} de ${days} dias` : ""}</span>
      </div>
      {row && (
        <div className="money">
          <div>
            <span className="money-label">{cost == null ? "Renda por mês" : "Lucro por mês"}</span>
            <strong className={`money-value ${(headline ?? 0) >= 0 ? "tone-good" : "tone-bad"}`}>{usd(headline)}</strong>
            <span className="muted small">{num(row.gems_per_day)} gemas/dia · 24 h/dia: {usd(cost == null ? row.income_usd_24h : row.profit_usd_24h)}</span>
          </div>
          <div className="money-bars">
            <Bar value={income} max={max} tone="good" label={<>Renda <strong>{usd(income)}</strong></>} />
            {cost != null && <Bar value={cost} max={max} tone="critical" label={<>Custo <strong>{usd(cost)}</strong></>} />}
          </div>
        </div>
      )}
      <p className="small secondary" style={{ margin: 0 }}>
        Já recebido no Mercado ({SALES_DAYS} dias): <strong className="num">{received == null ? <Ld w="4ch" /> : num(received)}</strong> gemas
        {received != null && received > 0 && <> · {usd(received * USD_PER_ORB)}</>}
      </p>
    </section>
  );
}

function SalesBlock({ d, conta, nicks }: { d: Awaited<ReturnType<typeof loadSales>> | undefined; conta: string | null; nicks: Map<string, string> }) {
  const rows = d?.rows ?? [];
  const open = rows.filter((l) => l.status === "aberto");
  const closed = rows.filter((l) => l.status !== "aberto");
  const soldUnits = rows.reduce((s, l) => s + l.soldQty, 0);
  const listedGems = open.filter((l) => l.currency === "orb").reduce((s, l) => s + l.qty * (l.price ?? 0), 0);
  const v = (x: React.ReactNode) => (d ? x : <Ld />);
  const showNicks = conta ? null : nicks;
  return (
    <>
      <div className="kpis">
        <Kpi label="Anúncios abertos" value={v(num(open.length))} note={d ? `${num(open.reduce((s, l) => s + l.qty, 0))} unidades` : undefined} />
        <Kpi label="Gemas anunciadas" value={v(num(listedGems))} tone="gem" />
        <Kpi label="Vendidas" value={v(num(soldUnits))} note={`${SALES_DAYS} dias`} />
      </div>
      {d && d.sellers.length > 0 && (
        <p className="seller-chips small">
          {d.sellers.map((s) => {
            const on = s.enabled && s.config?.dry_run === false;
            return (
              <span key={s.account_id} className={`chip ${on ? "is-on" : ""}`} title="Plugin seller desta conta">
                <span className="status-dot" aria-hidden />{nicks.get(s.account_id)}: {!s.enabled ? "desligado" : on ? "vendendo" : "simulação"}
              </span>
            );
          })}
        </p>
      )}
      <Panel title="Anúncios abertos" meta={d ? `lista do jogo ${ago(d.lastMine)}` : undefined} flush>
        {d && open.length === 0
          ? <p className="panel-empty">Nenhum anúncio aberto.</p>
          : <ListingTable rows={d ? open : null} nicks={showNicks} open />}
      </Panel>
      {d && closed.length > 0 && (
        <Fold title="Vendidos e cancelados" meta={num(closed.length)} flush>
          <ListingTable rows={closed} nicks={showNicks} />
        </Fold>
      )}
      {d && (d.plans.length > 0 || d.activity.length > 0) && (
        <Fold title="O que o seller fez" meta={d.activity[0] ? ago(d.activity[0].at) : undefined}>
          {d.plans.map((p) => (
            <div key={p.accountId} className="stack" style={{ gap: ".4rem" }}>
              <strong className="small">Último ciclo{!conta && <> · {nicks.get(p.accountId)}</>} <span className="muted">· {ago(p.at)}</span></strong>
              <StoneTable stones={p.stones} />
            </div>
          ))}
          {d.activity.length > 0 && <ActivityList items={d.activity.slice(0, 30)} nicks={conta ? null : nicks} />}
          {d.notices.length > 0 && (
            <>
              <strong className="small">Avisos do jogo</strong>
              <ul className="activity">
                {d.notices.map((e, i) => (
                  <li key={i}><span className="muted num">{dateTime(e.at)}</span><span><strong>{e.t}</strong> {e.text}</span></li>
                ))}
              </ul>
            </>
          )}
        </Fold>
      )}
    </>
  );
}

/** Drops dos últimos 7 dias pelo preço de hoje; as pedras aparecem apagadas e fora do total. */
function DropsBlock({ d }: { d: Awaited<ReturnType<typeof loadMarket>> | undefined }) {
  const rows = d?.rows ?? [];
  const income = rows.filter((r) => !r.stone);
  const totalOrb = income.reduce((s, r) => s + r.qty * orbOf(r), 0);
  const totalGold = rows.reduce((s, r) => s + r.qty * goldOf(r), 0);
  const maxOrb = Math.max(0, ...income.map((r) => r.qty * orbOf(r)));
  const stones = rows.filter((r) => r.stone).reduce((s, r) => s + r.qty, 0);
  return (
    <Panel title={`Drops de ${MARKET_DAYS} dias`} flush meta={d ? <>
      <strong className="num gem-text">{num(totalOrb)}</strong> gemas · <span className="num gold-text">{num(totalGold, { compact: true })}</span> ouro
    </> : <Ld w="10ch" />}>
      {d && rows.length === 0 ? <p className="panel-empty">Nenhum drop nos últimos {MARKET_DAYS} dias.</p> : (
        <table>
          <thead><tr><th>Item</th><th className="r">Unidades</th><th className="r">Gemas/un.</th><th>Valor em gemas</th></tr></thead>
          <tbody>
            {!d && <LdRows cols={4} rows={5} />}
            {rows.map((r) => <DropRow key={r.name} r={r} max={maxOrb} />)}
          </tbody>
        </table>
      )}
      {stones > 0 && <p className="small muted" style={{ margin: 0, padding: ".6rem 1rem" }}>{num(stones)} pedras ficaram fora do total (não são fonte de gemas).</p>}
    </Panel>
  );
}

function DropRow({ r, max }: { r: Row; max: number }) {
  const info = [
    r.ref ? `mediana ${num(r.ref.median)} (${num(r.ref.sales)} vendas)` : null,
    r.orb ? `média do jogo ${num(r.orb.avg)}` : null,
    r.ask?.min != null ? `menor anúncio ${num(r.ask.min)}, fila ${num(r.ask.queue)}` : null,
  ].filter(Boolean).join(" · ");
  const value = r.qty * orbOf(r);
  return (
    <tr className={r.stone ? "is-muted" : undefined}>
      <td><span className="sale-item"><ItemIcon src={r.icon} name={r.name} size={24} />{r.name}</span>
        {r.stone && <span className="tag-off">fora da renda</span>}</td>
      <td className="r">{num(r.qty)}</td>
      <td className="r" title={info || undefined}>{num(orbOf(r))}</td>
      <td>{r.stone ? <span className="muted num">{num(value)}</span> : <Bar value={value} max={max} tone="gem" label={num(value)} />}</td>
    </tr>
  );
}

function PerAccount({ rows }: { rows: EvalRow[] }) {
  const max = Math.max(0, ...rows.map((r) => r.gems_per_day ?? 0));
  return (
    <Fold title="Por conta" meta="renda dos drops, sem pedras" flush>
      <table>
        <thead><tr><th>Conta</th><th>Gemas/dia</th><th className="r">Gemas/h ativa</th><th className="r">Renda/mês</th></tr></thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.account_id}>
              <td>{a.nick}</td>
              <td><Bar value={a.gems_per_day} max={max} tone="gem" label={num(a.gems_per_day)} /></td>
              <td className="r">{num(a.gems_per_hour)}</td>
              <td className="r">{usd(a.income_usd_as_is)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Fold>
  );
}

function ActivityList({ items, nicks }: { items: Activity[]; nicks: Map<string, string> | null }) {
  return (
    <ul className="activity">
      {items.map((a, i) => (
        <li key={i} className={a.tone}>
          <span className="muted num">{dateTime(a.at)}</span>
          <span>{nicks && <>{nicks.get(a.accountId)}: </>}{a.text}</span>
        </li>
      ))}
    </ul>
  );
}

function ListingTable({ rows, nicks, open = false }: { rows: SaleRow[] | null; nicks: Map<string, string> | null; open?: boolean }) {
  const cols = 4 + (nicks ? 1 : 0) + (open ? 0 : 1);
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
            <th>{open ? "Anunciado" : "Situação"}</th>
          </tr>
        </thead>
        <tbody>
          {!rows && <LdRows cols={cols} rows={3} />}
          {rows?.map((l) => (
            <tr key={l.id}>
              <td><span className="sale-item"><ItemIcon src={l.icon} name={l.label} size={24} />{l.label}</span></td>
              {nicks && <td>{nicks.get(l.accountId)}</td>}
              <td className="r">{num(open ? l.qty : l.firstQty)}</td>
              {!open && <td className="r">{num(l.soldQty)}</td>}
              <td className="r">{l.price == null ? "—" : `${num(l.price)} ${l.currency === "orb" ? "gemas" : "ouro"}`}</td>
              <td>
                {open ? <span className="small">{dateTime(l.createdAt)}</span> : (
                  <span className={`sale-status sale-${l.status.replace("?", "")}`}>
                    {STATUS_LABEL[l.status]}{l.gameState && l.status === "outro" && ` (${l.gameState})`}
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

const DECISION_LABEL: Record<string, string> = {
  guarda_fila_longa: "Guarda: fila parada",
  guarda_abaixo_do_piso: "Guarda: abaixo do piso",
  sem_media: "Guarda: sem preço",
  sem_leitura_de_anuncios: "Espera: sem leitura",
  anunciado: "Anuncia",
  reprecificado: "Reprecifica",
  lote_novo: "Lote novo",
  limite_de_anuncios: "Guarda: 20 anúncios",
  ok: "Nada a fazer",
};

/** As decisões do último ciclo do seller, pedra a pedra (docs/design/seller-liquidez.md). */
function StoneTable({ stones }: { stones: Stone[] }) {
  if (stones.length === 0) return <p className="small muted" style={{ margin: 0 }}>Nenhuma pedra acima da reserva.</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr><th>Pedra</th><th className="r">Estoque</th><th className="r">Anunciado</th><th className="r">Menor anúncio</th><th className="r">Dias p/ vender</th><th>Decisão</th></tr>
        </thead>
        <tbody>
          {stones.map((s) => (
            <tr key={s.item_id}>
              <td>{s.name}</td>
              <td className="r">{num(s.stock)}</td>
              <td className="r">{num(s.listed)}</td>
              <td className="r" title={s.ahead != null ? `fila à frente: ${num(s.ahead)}` : undefined}>{num(s.min_ask)}</td>
              <td className="r">{s.days_to_sell === undefined ? "—" : s.days_to_sell === null ? "∞" : num(s.days_to_sell)}</td>
              <td className={s.decision?.startsWith("guarda") ? "muted" : undefined}>{DECISION_LABEL[s.decision ?? ""] ?? s.decision ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

