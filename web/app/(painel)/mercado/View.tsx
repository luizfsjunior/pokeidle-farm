"use client";

import { useSearchParams } from "next/navigation";
import { ItemIcon } from "@/components/ItemIcon";
import { Ld, LdRows } from "@/components/Loading";
import { AccountTabs, ErrorNote, Explain, Kpi, PageHeader, Panel } from "@/components/Page";
import { dateTime, num } from "@/lib/format";
import { useAccounts, usePanel } from "@/lib/query/hooks";
import { DAYS, goldOf, loadMarket, MIN_SALES, orbOf } from "./data";

export function MarketView() {
  const sp = useSearchParams();
  const accountsQ = useAccounts();
  const accounts = accountsQ.data ?? [];
  const chosen = accounts.find((a) => a.id === sp.get("conta")) ?? null;
  const { data: d } = usePanel(["mercado", chosen?.id ?? null], (sb) => loadMarket(sb, chosen?.id ?? null), { enabled: accountsQ.isSuccess });

  const rows = d?.rows ?? [];
  const totalOrb = rows.reduce((s, r) => s + r.qty * orbOf(r), 0);
  const totalGold = rows.reduce((s, r) => s + r.qty * goldOf(r), 0);
  const v = (x: React.ReactNode) => (d ? x : <Ld />);

  return (
    <>
      <PageHeader
        title="Mercado"
        subtitle={<>Quanto valem os drops dos últimos {DAYS} dias{chosen ? ` de ${chosen.nick}` : ""}, em gemas e em ouro.{" "}
          {d ? (d.takenAt ? `Preços de ${dateTime(d.takenAt)}.` : "Ainda sem preços do Mercado.") : null}</>}
      >
        <AccountTabs accounts={accounts} chosen={chosen?.id ?? null} href={(id) => (id ? `/mercado?conta=${id}` : "/mercado")} />
      </PageHeader>
      <ErrorNote message={d?.err ?? accountsQ.error?.message} />
      <div className="stack">
        <div className="kpis">
          <Kpi label="Valor em gemas" value={v(num(totalOrb))} tone="gem" />
          <Kpi label="Valor em ouro" value={v(num(totalGold, { compact: true }))} tone="gold" />
          <Kpi label="Itens diferentes" value={v(num(rows.length))} />
        </div>
        <Explain>
          <p>Gemas: a mediana das vendas reais dos últimos 7 dias, sem outliers nem transferências, ou a média do jogo
            com menos de {MIN_SALES} vendas; limitada pelo menor anúncio aberto, que é o preço pelo qual vende hoje.</p>
          <p>Ouro: a média do Mercado. Sem vendas em ouro, vale o preço do NPC (marcado com *).</p>
          <p>Média em destaque: mais que o dobro da mediana, sinal de vendas fora da curva. As métricas usam o preço da hora
            de cada drop.</p>
        </Explain>
        {d && rows.length === 0 ? (
          <div className="panel"><p className="panel-empty">Nenhum drop nos últimos {DAYS} dias.</p></div>
        ) : (
          <Panel title="Drops por item" flush>
            <table>
              <thead>
                <tr>
                  <th>Item</th><th>Unidades</th><th>Gemas (média)</th><th>Gemas (mediana das vendas)</th><th>Menor anúncio (fila)</th><th>Vendidas</th>
                  <th>Ouro (média)</th><th>Vendidas</th><th>Valor (gemas)</th><th>Valor (ouro)</th>
                </tr>
              </thead>
              <tbody>
                {!d && <LdRows cols={10} rows={6} />}
                {rows.map((r) => (
                  <tr key={r.name}>
                    <td><span className="sale-item"><ItemIcon src={r.icon} name={r.name} size={24} />{r.name}</span>{r.itemId === null && <span className="error small"> · fora do catálogo</span>}</td>
                    <td>{num(r.qty)}</td>
                    <td className={r.ref && r.orb && r.orb.avg > r.ref.median * 2 ? "warn" : undefined}>{r.orb ? num(r.orb.avg) : "—"}</td>
                    <td>{r.ref ? <>{num(r.ref.median)} <span className="muted small">({num(r.ref.sales)} vendas)</span></> : "—"}</td>
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
          </Panel>
        )}
      </div>
    </>
  );
}
