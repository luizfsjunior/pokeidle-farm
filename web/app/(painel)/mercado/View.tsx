"use client";

import { useSearchParams } from "next/navigation";
import { ItemIcon } from "@/components/ItemIcon";
import { Ld, LdRows } from "@/components/Loading";
import { AccountTabs, Bar, ErrorNote, Kpi, PageHeader, Panel } from "@/components/Page";
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
  const maxOrb = Math.max(0, ...rows.map((r) => r.qty * orbOf(r)));

  return (
    <>
      <PageHeader
        title="Mercado"
        subtitle={`Drops de ${DAYS} dias${d?.takenAt ? ` · preços de ${dateTime(d.takenAt)}` : ""}`}
        hint={<>
          <p>Gemas: a mediana das vendas reais de 7 dias (sem outliers), ou a média do jogo com menos de {MIN_SALES} vendas,
            limitada pelo menor anúncio aberto.</p>
          <p>Ouro: a média do Mercado; sem vendas em ouro, o preço do NPC (*).</p>
          <p>Passe o dedo ou o mouse no preço para ver média, mediana e fila.</p>
        </>}
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
        {d && rows.length === 0 ? (
          <div className="panel"><p className="panel-empty">Nenhum drop nos últimos {DAYS} dias.</p></div>
        ) : (
          <Panel title="Drops por item" flush>
            <table>
              <thead>
                <tr><th>Item</th><th className="r">Unidades</th><th className="r">Gemas/un.</th><th>Valor em gemas</th><th className="r">Valor em ouro</th></tr>
              </thead>
              <tbody>
                {!d && <LdRows cols={5} rows={6} />}
                {rows.map((r) => {
                  const priceInfo = [
                    r.orb ? `média ${num(r.orb.avg)} (${num(r.orb.units)} vendidas)` : null,
                    r.ref ? `mediana ${num(r.ref.median)} (${num(r.ref.sales)} vendas)` : null,
                    r.ask?.min != null ? `menor anúncio ${num(r.ask.min)}, fila ${num(r.ask.queue)}` : null,
                  ].filter(Boolean).join(" · ");
                  return (
                    <tr key={r.name}>
                      <td><span className="sale-item"><ItemIcon src={r.icon} name={r.name} size={24} />{r.name}</span>{r.itemId === null && <span className="error small"> · fora do catálogo</span>}</td>
                      <td className="r">{num(r.qty)}</td>
                      <td className={`r ${r.ref && r.orb && r.orb.avg > r.ref.median * 2 ? "warn" : ""}`} title={priceInfo || undefined}>{num(orbOf(r))}</td>
                      <td><Bar value={r.qty * orbOf(r)} max={maxOrb} tone="gem" label={num(r.qty * orbOf(r))} /></td>
                      <td className="r" title={r.gold ? `média ${num(r.gold.avg, { compact: true })}` : r.npc != null ? "preço do NPC" : undefined}>
                        {num(r.qty * goldOf(r), { compact: true })}{!r.gold && r.npc != null ? "*" : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Panel>
        )}
      </div>
    </>
  );
}
