"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { Ld, LdBlock, LdRows } from "@/components/Loading";
import { Bar, ErrorNote, PageHeader, Panel } from "@/components/Page";
import { num } from "@/lib/format";
import { usePanel } from "@/lib/query/hooks";
import { OutlandCard, type OutlandPotentialData } from "../contas/[id]/OutlandCard";
import { SettingsForm, type EvalSettings } from "./SettingsForm";

type Summary = {
  kind: "account" | "total" | "three_accounts";
  account_id: string | null;
  nick: string | null;
  gems: number | null;
  gold: number | null;
  active_hours: number | null;
  data_days: number | null;
  gems_per_day: number | null;
  gems_per_hour: number | null;
  month_gems_as_is: number | null;
  month_gems_24h: number | null;
  income_usd_as_is: number | null;
  income_usd_24h: number | null;
  cost_usd: number | null;
  profit_usd_as_is: number | null;
  profit_usd_24h: number | null;
};
type Liquidity = {
  name: string;
  item_id: number | null;
  dropped: number;
  dropped_week: number;
  sold_week: number | null;
  share: number | null;
  flagged: boolean;
};

const usd = (v: number | null | undefined) =>
  v == null ? "—" : `US$ ${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)}`;

async function loadEvaluation(supabase: SupabaseClient) {
  const settingsRes = await supabase.from("evaluation_settings")
    .select("machine_watts, marginal, kwh_price_brl, usd_brl, fixed_cost_usd, window_days").maybeSingle<EvalSettings>();
  const settings: EvalSettings = settingsRes.data ?? {
    machine_watts: null, marginal: false, kwh_price_brl: null, usd_brl: null, fixed_cost_usd: null, window_days: 7,
  };
  const days = settings.window_days;
  const [sumRes, liqRes, potRes] = await Promise.all([
    supabase.rpc("evaluation_summary", { p_days: days }),
    supabase.rpc("evaluation_liquidity", { p_days: days }),
    supabase.from("events").select("received_at, data").eq("type", "outland.potential")
      .order("received_at", { ascending: false }).limit(1).maybeSingle(),
  ]);
  const potential: OutlandPotentialData | null = potRes.data
    ? { at: potRes.data.received_at as string, ...(potRes.data.data as Omit<OutlandPotentialData, "at">) }
    : null;
  const rows = (sumRes.data ?? []) as Summary[];
  return {
    settings,
    potential,
    accounts: rows.filter((r) => r.kind === "account"),
    total: rows.find((r) => r.kind === "total") ?? null,
    three: rows.find((r) => r.kind === "three_accounts") ?? null,
    liquidity: (liqRes.data ?? []) as Liquidity[],
    err: sumRes.error?.message ?? liqRes.error?.message ?? settingsRes.error?.message ?? null,
  };
}

/** "Compensa?" (docs/design/fase-8-compensa.md): renda em gemas dos drops contra o custo de energia. */
export function EvaluationView() {
  const { data: d } = usePanel(["compensa"], loadEvaluation);
  const days = d?.settings.window_days ?? 7;
  const total = d?.total ?? null;
  const enoughData = (total?.data_days ?? 0) >= days - 0.05;
  const costKnown = total?.cost_usd != null;
  const profit = total?.profit_usd_as_is ?? null;
  const verdict = !d ? <Ld w="14ch" />
    : !total ? "Sem dados ainda"
    : !enoughData ? "Dados insuficientes"
    : (profit ?? 0) > 0 ? "Compensa" : "Não compensa";

  return (
    <>
      <PageHeader title="Compensa?" subtitle={`Renda contra custo · últimos ${days} dias`} hint={<>
        <p>Renda = gemas dos drops por mês × (1 − 15% de comissão) × US$ 0,009 por gema (saque).</p>
        <p>Supõe vender tudo pelo preço de referência. O ouro não sai do jogo e não entra na renda.</p>
        <p>Conta a partir do primeiro preço do Mercado.</p>
      </>} />
      <ErrorNote message={d?.err} />
      <div className="stack">

        <section className="card stack verdict">
          <div className="spread">
            <h2 style={{ margin: 0 }}>{verdict}</h2>
            <span className="muted small">{total ? `${num(total.data_days)}/${days} dias` : ""}</span>
          </div>
          {!d && <LdBlock h={150} />}
          {total && (
            <>
              <div className="money">
                <div>
                  <span className="money-label">Lucro por mês</span>
                  <strong className={`money-value ${(profit ?? 0) >= 0 ? "tone-good" : "tone-bad"}`}>{usd(profit)}</strong>
                  <span className="muted small">24 h/dia: {usd(total.profit_usd_24h)}</span>
                </div>
                <div className="money-bars">
                  <Bar value={total.income_usd_as_is} max={Math.max(total.income_usd_as_is ?? 0, total.cost_usd ?? 0)} tone="good"
                    label={<>Renda <strong>{usd(total.income_usd_as_is)}</strong></>} />
                  <Bar value={total.cost_usd} max={Math.max(total.income_usd_as_is ?? 0, total.cost_usd ?? 0)} tone="critical"
                    label={<>Custo <strong>{costKnown ? usd(total.cost_usd) : "não informado"}</strong></>} />
                </div>
              </div>
              <div className="stats">
                <Stat label="Gemas por dia" value={num(total.gems_per_day)} />
                <Stat label="Gemas no mês (como está)" value={num(total.month_gems_as_is)} />
                <Stat label="Gemas no mês (24 h/dia)" value={num(total.month_gems_24h)} />
                <Stat label="Renda (24 h/dia)" value={usd(total.income_usd_24h)} />
                {d?.three && <Stat label="Lucro com 3 contas (como está)" value={usd(d.three!.profit_usd_as_is)} />}
                {d?.three && <Stat label="Lucro com 3 contas (24 h/dia)" value={usd(d.three!.profit_usd_24h)} />}
              </div>
            </>
          )}
        </section>

        {d?.potential && (
          <div>
            <p className="muted small" style={{ margin: "0 0 .5rem" }}>
              O que deve render quando uma conta chegar na Outland:
            </p>
            <OutlandCard data={d.potential} />
          </div>
        )}

        {(!d || d.accounts.length > 0) && (
          <Panel title="Por conta" flush>
            <table>
              <thead>
                <tr>
                  <th>Conta</th><th>Dias de dado</th><th>Horas ativas</th><th>Gemas</th><th>Gemas/dia</th>
                  <th>Gemas/h ativa</th><th>Renda/mês (como está)</th><th>Renda/mês (24 h)</th><th>Ouro dos drops</th>
                </tr>
              </thead>
              <tbody>
                {!d && <LdRows cols={9} rows={1} />}
                {d?.accounts.map((a) => (
                  <tr key={a.account_id}>
                    <td>{a.nick}</td>
                    <td>{num(a.data_days)}</td>
                    <td>{num(a.active_hours)}</td>
                    <td>{num(a.gems)}</td>
                    <td>{num(a.gems_per_day)}</td>
                    <td>{num(a.gems_per_hour)}</td>
                    <td>{usd(a.income_usd_as_is)}</td>
                    <td>{usd(a.income_usd_24h)}</td>
                    <td>{num(a.gold, { compact: true })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        )}

        {(!d || d.liquidity.length > 0) && (
          <Panel title="Liquidez" meta="por semana" flush hint="Parcela = dropado ÷ vendido no Mercado. Acima de 10%, vender tudo pela média é otimista.">
            <table>
              <thead><tr><th>Item</th><th>Dropado/semana</th><th>Vendido/semana</th><th>Parcela</th></tr></thead>
              <tbody>
                {!d && <LdRows cols={4} rows={4} />}
                {d?.liquidity.map((l) => (
                  <tr key={l.name}>
                    <td>{l.name}</td>
                    <td>{num(l.dropped_week)}</td>
                    <td>{l.sold_week == null ? "sem vendas" : num(l.sold_week)}</td>
                    <td className={l.flagged ? "error" : ""}>
                      {l.share == null ? "—" : <Bar value={l.share} max={0.1} tone={l.flagged ? "critical" : "good"} label={`${num(l.share * 100)}%`} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        )}

        {d && <SettingsForm initial={d.settings} />}
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
