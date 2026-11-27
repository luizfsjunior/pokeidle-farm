"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { LdBlock, LdRows } from "@/components/Loading";
import { ErrorNote, LinkTabs, PageHeader, Panel } from "@/components/Page";
import { TrendChart } from "@/components/TrendChart";
import { nickBadge, num, pct } from "@/lib/format";
import { useAccounts, usePanel } from "@/lib/query/hooks";
import { loadHistory, PERIODS, type Day, type Period, type Summary } from "./data";

type Measure = {
  key: string;
  label: string;
  tone: "accent" | "gold" | "gem" | "diamond" | "good";
  compact?: boolean;
  value: (d: Day) => number | null;
  flow: boolean; // fluxo (soma por dia: o rodapé mostra o total) ou retrato (nível, gemas: o rodapé mostra a variação)
};

/** As medidas do gráfico: uma por vez, as contas lado a lado na mesma escala. */
const MEASURES: Measure[] = [
  { key: "xp", label: "XP por dia", tone: "diamond", compact: true, value: (d) => d.xp, flow: true },
  { key: "ouro", label: "Ouro líquido por dia", tone: "gold", compact: true, value: (d) => d.gold_net, flow: true },
  { key: "capturas", label: "Capturas por dia", tone: "good", value: (d) => d.captures, flow: true },
  { key: "abates", label: "Abates por dia", tone: "accent", compact: true, value: (d) => d.kills, flow: true },
  { key: "horas", label: "Horas ativas por dia", tone: "accent", value: (d) => d.active_minutes / 60, flow: true },
  { key: "quedas", label: "Desconexões por dia", tone: "accent", value: (d) => d.disconnects, flow: true },
  { key: "nivel", label: "Nível", tone: "accent", value: (d) => d.level, flow: false },
  { key: "gemas", label: "Gemas na conta", tone: "gem", value: (d) => d.gems, flow: false },
];

const perHour = (v: number, mins: number) => (mins > 0 ? (v * 60) / mins : null);
const delta = (a: number | null, b: number | null) => (a == null || b == null ? null : b - a);
const signed = (v: number | null, compact = false) => (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${num(Math.abs(v), { compact })}`);

/**
 * Histórico (docs/design/historico.md): as contas lado a lado em 7, 30 ou 90 dias. Os números saem de
 * agregados por hora e por dia (`account_history`), nunca dos eventos crus.
 */
export function HistoryView() {
  const sp = useSearchParams();
  const dias = sp.get("dias");
  const period: Period = dias === "7" || dias === "90" ? dias : "30";
  const measure = MEASURES.find((m) => m.key === sp.get("medida")) ?? MEASURES[0];
  const accountsQ = useAccounts();
  const farm = (accountsQ.data ?? []).filter((a) => a.role === "farm");
  const q = usePanel(["history", period], (sb) => loadHistory(sb, period), { refetchInterval: 10 * 60_000 });
  const d = q.data;

  const link = (over: { dias?: string; medida?: string }) => {
    const p = new URLSearchParams();
    const ds = over.dias ?? period;
    const md = over.medida ?? measure.key;
    if (ds !== "30") p.set("dias", ds);
    if (md !== MEASURES[0].key) p.set("medida", md);
    const s = p.toString();
    return s ? `/historico?${s}` : "/historico";
  };

  const rows = farm.map((a) => ({ a, s: d?.get(a.id) })).filter((r): r is { a: typeof farm[number]; s: Summary } => !!r.s);
  // escala comum: as contas comparam de verdade (cada gráfico com a própria escala engana)
  const all = rows.flatMap((r) => r.s.days.map(measure.value)).filter((v): v is number => v != null);
  const domain: [number, number] | undefined = all.length ? [Math.min(0, ...all), Math.max(...all)] : undefined;
  const sharedDomain = measure.flow ? domain : undefined; // nível e gemas: cada conta na sua faixa

  return (
    <>
      <PageHeader title="Histórico" subtitle={`Últimos ${PERIODS[period]}, por dia de Brasília`}
        hint={<><p>XP, ouro, capturas, abates, horas e desconexões vêm das métricas por hora (recalculadas a cada 10 min) e,
          depois de 95 dias, do arquivo por dia. Nível e gemas são o retrato do perfil no fim de cada dia.</p>
          <p>Ouro líquido: o dos abates menos bolas, poções e revives gastos, a preço da loja. O dia de hoje ainda está
          em andamento.</p></>}>
        <LinkTabs label="Período" items={(Object.keys(PERIODS) as Period[]).map((p) => ({ key: p, href: link({ dias: p }), label: PERIODS[p], active: p === period }))} />
      </PageHeader>
      <ErrorNote message={q.error?.message ?? accountsQ.error?.message} />

      <Panel title="No período" flush
        meta={<Link href={`/hunts${period === "7" ? "" : `?dias=${period}`}`}>Desempenho por hunt →</Link>}>
        {!d ? <div className="panel-body"><LdRows cols={1} rows={4} /></div> : (
          <div className="table-scroll">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Conta</th><th className="r">Nível</th><th className="r">XP</th><th className="r">XP/h</th>
                  <th className="r">Ouro líq.</th><th className="r">Ouro líq./h</th><th className="r">Capturas</th>
                  <th className="r">Horas ativas</th><th className="r">Desconexões</th><th className="r">Gemas</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ a, s }) => {
                  const lv = delta(s.levelFrom, s.levelTo);
                  return (
                    <tr key={a.id}>
                      <td><Link href={`/contas/${a.id}`} className="acc-nick"><span className="tab-avatar" aria-hidden>{nickBadge(a.nick)}</span>{a.nick}</Link></td>
                      <td className="r num" title={s.levelFrom != null ? `de ${s.levelFrom} para ${s.levelTo}` : undefined}>
                        {s.levelTo ?? "—"}{lv ? <span className="muted small"> ({signed(lv)})</span> : null}
                      </td>
                      <td className="r num">{num(s.xp, { compact: true })}</td>
                      <td className="r num">{num(perHour(s.xp, s.minutes), { compact: true })}</td>
                      <td className="r num">{num(s.goldNet, { compact: true })}</td>
                      <td className="r num">{num(perHour(s.goldNet, s.minutes), { compact: true })}</td>
                      <td className="r num" title={s.attempts ? `${num(s.attempts)} bolas, ${pct(s.captures / s.attempts)} de acerto` : undefined}>
                        {num(s.captures)}{s.shinies > 0 && <span className="small"> ({num(s.shinies)} ✨)</span>}
                      </td>
                      <td className="r num" title="Minutos com pelo menos um abate">
                        {num(s.minutes / 60)} h<span className="muted small"> ({pct(s.minutes / (s.days.length * 1440), 0)})</span>
                      </td>
                      <td className="r num">{num(s.disconnects)}</td>
                      <td className="r num" title={`gemas na conta; drops do período valem ${num(s.gemsDrops)} gemas no Mercado`}>
                        {num(s.gemsTo)}{delta(s.gemsFrom, s.gemsTo) ? <span className="muted small"> ({signed(delta(s.gemsFrom, s.gemsTo))})</span> : null}
                      </td>
                    </tr>
                  );
                })}
                {rows.length === 0 && <tr><td colSpan={10} className="muted">Sem dados no período.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Por dia">
        <LinkTabs label="Medida" items={MEASURES.map((m) => ({ key: m.key, href: link({ medida: m.key }), label: m.label, active: m.key === measure.key }))} />
        <div className="trends" style={{ marginTop: "1rem" }}>
          {!d && farm.map((a) => <LdBlock key={a.id} h={170} />)}
          {d && rows.map(({ a, s }) => {
            const points = s.days.map((x) => ({ day: x.day, value: measure.value(x) }));
            const vals = points.map((p) => p.value).filter((v): v is number => v != null);
            const total = vals.reduce((t, v) => t + v, 0);
            return (
              <TrendChart key={a.id} title={a.nick} points={points} tone={measure.tone} compact={measure.compact}
                domain={sharedDomain}
                foot={measure.flow ? <>{num(total, { compact: measure.compact })} no período · {num(total / Math.max(1, s.days.length), { compact: measure.compact })}/dia</> : undefined} />
            );
          })}
        </div>
      </Panel>
    </>
  );
}
