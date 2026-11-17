"use client";

import { useSearchParams } from "next/navigation";
import { ItemIcon } from "@/components/ItemIcon";
import { Ld, LdRows } from "@/components/Loading";
import { AccountTabs, ErrorNote, Explain, Kpi, PageHeader, Panel } from "@/components/Page";
import { ago, dateTime, num } from "@/lib/format";
import { useAccounts, usePanel } from "@/lib/query/hooks";
import { MARKET_FEE, STATUS_LABEL } from "@/lib/sales";
import { DAYS, loadSales, type Activity, type SaleRow, type Stone } from "./data";

/** Anúncios das contas no Mercado: abertos, vendidos e cancelados, e o que o seller fez (docs/design/pagina-vendas.md). */
export function SalesView() {
  const sp = useSearchParams();
  const accountsQ = useAccounts();
  const accounts = accountsQ.data ?? [];
  const conta = accounts.find((a) => a.id === sp.get("conta"))?.id ?? null;
  const nicks = new Map(accounts.map((a) => [a.id, a.nick]));
  const { data: d } = usePanel(["vendas", conta], (sb) => loadSales(sb, conta), { enabled: accountsQ.isSuccess });

  const rows = d?.rows ?? [];
  const open = rows.filter((l) => l.status === "aberto");
  const closed = rows.filter((l) => l.status !== "aberto");
  const sold = rows.filter((l) => l.soldQty > 0);
  const gemsOf = (ls: SaleRow[], qty: (l: SaleRow) => number) =>
    ls.filter((l) => l.currency === "orb").reduce((s, l) => s + qty(l) * (l.price ?? 0), 0);
  const v = (x: React.ReactNode) => (d ? x : <Ld />);
  const showNicks = conta ? null : nicks;

  return (
    <>
      <PageHeader
        title="Vendas"
        subtitle={`Últimos ${DAYS} dias${d?.lastMine ? ` · lista do jogo ${ago(d.lastMine)}` : ""}`}
      >
        <AccountTabs accounts={accounts} chosen={conta} href={(id) => (id ? `/vendas?conta=${id}` : "/vendas")} />
      </PageHeader>
      <ErrorNote message={d?.err ?? accountsQ.error?.message} />

      <div className="stack">
        <div className="kpis">
          <Kpi label="Anúncios abertos" value={v(num(open.length))} note={d ? `${num(open.reduce((s, l) => s + l.qty, 0))} unidades` : <Ld w="7ch" />} />
          <Kpi label="Gemas anunciadas" value={v(num(gemsOf(open, (l) => l.qty)))} tone="gem" />
          <Kpi label="Unidades vendidas" value={v(num(sold.reduce((s, l) => s + l.soldQty, 0)))} />
          <Kpi label="Gemas recebidas" value={v(num(gemsOf(sold, (l) => l.soldQty) * (1 - MARKET_FEE)))} tone="gem" note={`já sem os ${MARKET_FEE * 100}% de taxa`} />
        </div>
        {d?.sellers.map((s) => (
          <p key={s.account_id} className={`status-line ${s.enabled && s.config?.dry_run === false ? "is-on" : ""}`}>
            <span className="status-dot" aria-hidden />
            <span><strong>{nicks.get(s.account_id)}</strong> · seller {!s.enabled ? "desligado" : s.config?.dry_run !== false ? <span className="badge" title="só registra o que faria, sem anunciar">simulação</span> : "vendendo"}</span>
          </p>
        ))}

        {d?.plans.map((p) => {
          const cfg = d.sellers.find((s) => s.account_id === p.accountId)?.config;
          return (
            <Panel key={p.accountId} title={<>Seller{!conta && <> · {nicks.get(p.accountId)}</>}</>}
              meta={ago(p.at)} flush hint={<>
                <p>Só anuncia se a fila à frente mais o lote vende em até {num(Number(cfg?.max_days ?? 3))} dias, pelo volume
                  vendido na semana.</p>
                <p>O piso ({num(Number(cfg?.floor_ratio ?? 0.85) * 100)}%) é da menor entre a média do jogo e a mediana das vendas.</p>
              </>}>
              <StoneTable stones={p.stones} />
            </Panel>
          );
        })}

        <div className="cols-2">
          <Panel title="Abertos" meta={v(num(open.length))} flush>
            {d && open.length === 0
              ? <p className="panel-empty">Nenhum anúncio aberto na última lista do jogo.</p>
              : <ListingTable rows={d ? open : null} nicks={showNicks} open />}
          </Panel>

          <Panel title="Vendidos e cancelados" meta={v(num(closed.length))} flush
            hint={<>&quot;Saiu da lista&quot;: o anúncio sumiu sem o worker cancelar. Quase sempre é venda, mas pode ter sido cancelado no navegador.</>}>
            {d && closed.length === 0
              ? <p className="panel-empty">Nada vendido ou cancelado no período.</p>
              : <ListingTable rows={d ? closed : null} nicks={showNicks} />}
          </Panel>
        </div>

        {d && d.notices.length > 0 && (
          <Panel title="Avisos do jogo">
            <ul className="activity">
              {d.notices.map((e, i) => (
                <li key={i}>
                  <span className="muted num">{dateTime(e.at)}</span>
                  <span><strong>{e.t}</strong> {e.text}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel title="Atividade" meta={d ? num(d.activity.length) : undefined}>
          {!d ? (
            <ul className="activity" aria-hidden>
              {[0, 1, 2, 3].map((i) => <li key={i}><Ld w="12ch" /><Ld w="24ch" /></li>)}
            </ul>
          ) : d.activity.length === 0 ? (
            <p className="muted small" style={{ margin: 0 }}>Nenhuma ação de Mercado no período.</p>
          ) : (
            <>
              <ActivityList items={d.activity.slice(0, 6)} nicks={conta ? null : nicks} />
              {d.activity.length > 6 && (
                <details className="more">
                  <summary>Ver as outras {num(d.activity.length - 6)}</summary>
                  <ActivityList items={d.activity.slice(6)} nicks={conta ? null : nicks} />
                </details>
              )}
            </>
          )}
        </Panel>

        <Explain title="Diagnóstico">
          <p>Respostas <code>market</code> por aba (últimas 500). A página usa <code>meus</code> e <code>criado</code>.</p>
          <ul className="small">
            {d && [...d.abaCount].map(([k, n]) => <li key={k}><code>{k}</code>: {num(n)}</li>)}
            {d && d.abaCount.size === 0 && <li className="muted">nenhuma</li>}
          </ul>
        </Explain>
      </div>
    </>
  );
}

/** Ações do worker no Mercado; as sondas e leituras de rotina ficam apagadas (tone "muted"). */
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
  const cols = 5 + (nicks ? 1 : 0) + (open ? 0 : 1);
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
          {!rows && <LdRows cols={cols} rows={3} />}
          {rows?.map((l) => (
            <tr key={l.id}>
              <td>
                <span className="sale-item">
                  <ItemIcon src={l.icon} name={l.label} size={24} />
                  {l.label}
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

const DECISION_LABEL: Record<string, string> = {
  guarda_fila_longa: "Guarda: fila parada",
  guarda_abaixo_do_piso: "Guarda: abaixo do piso",
  sem_media: "Guarda: sem preço de referência",
  sem_leitura_de_anuncios: "Espera: sem leitura",
  anunciado: "Anuncia",
  reprecificado: "Reprecifica",
  lote_novo: "Anuncia um lote novo",
  limite_de_anuncios: "Guarda: limite de 20 anúncios",
  ok: "Nada a fazer",
};

function StoneTable({ stones }: { stones: Stone[] }) {
  if (stones.length === 0) return <p className="panel-empty">Nenhuma pedra acima da reserva.</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Pedra</th><th className="r">Estoque</th><th className="r">Anunciado</th><th className="r">Referência</th>
            <th className="r">Menor anúncio</th><th className="r">Dias p/ vender</th><th className="r">Piso</th><th>Decisão</th>
          </tr>
        </thead>
        <tbody>
          {stones.map((s) => {
            const ref = s.ref_source === "median" ? s.median : s.avg;
            return (
              <tr key={s.item_id}>
                <td>{s.name}</td>
                <td className="r">{num(s.stock)}</td>
                <td className="r">{num(s.listed)}</td>
                <td className="r" title={s.ref_source === "median" ? `mediana de ${num(s.sales ?? 0)} vendas` : "média do jogo"}>{num(ref)}</td>
                <td className="r" title={s.ahead != null ? `fila à frente: ${num(s.ahead)}` : undefined}>{num(s.min_ask)}</td>
                <td className="r" title={s.per_day != null ? `${num(s.per_day)} vendidas por dia` : undefined}>
                  {s.days_to_sell === undefined ? "—" : s.days_to_sell === null ? "∞" : num(s.days_to_sell)}
                </td>
                <td className="r" title={s.floor_reason === "preco_estabelecido" ? "desceu ao preço do mercado" : undefined}>{num(s.floor)}</td>
                <td className={s.decision?.startsWith("guarda") ? "muted" : undefined}>{DECISION_LABEL[s.decision ?? ""] ?? s.decision ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
