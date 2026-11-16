import { ErrorNote, Explain, PageHeader, Panel } from "@/components/Page";
import { Shell } from "@/components/Shell";
import { num } from "@/lib/format";
import { requireUser } from "@/lib/supabase/server";
import { GemsCard, type GemsPotentialData } from "../contas/[id]/GemsCard";
import { SettingsForm, type EvalSettings } from "./SettingsForm";

export const dynamic = "force-dynamic";

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

/** "Compensa?" (docs/design/fase-8-compensa.md): renda em gemas dos drops contra o custo de energia. */
export default async function EvaluationPage() {
  const { supabase, email } = await requireUser();
  const settingsRes = await supabase.from("evaluation_settings")
    .select("machine_watts, marginal, kwh_price_brl, usd_brl, window_days").maybeSingle<EvalSettings>();
  const settings: EvalSettings = settingsRes.data ?? {
    machine_watts: null, marginal: false, kwh_price_brl: null, usd_brl: null, window_days: 7,
  };
  const days = settings.window_days;
  const [sumRes, liqRes, potRes] = await Promise.all([
    supabase.rpc("evaluation_summary", { p_days: days }),
    supabase.rpc("evaluation_liquidity", { p_days: days }),
    supabase.from("events").select("received_at, data").eq("type", "gems.potential")
      .order("received_at", { ascending: false }).limit(1).maybeSingle(),
  ]);
  const potential: GemsPotentialData | null = potRes.data
    ? { at: potRes.data.received_at as string, ...(potRes.data.data as Omit<GemsPotentialData, "at">) }
    : null;
  const rows = (sumRes.data ?? []) as Summary[];
  const accounts = rows.filter((r) => r.kind === "account");
  const total = rows.find((r) => r.kind === "total") ?? null;
  const three = rows.find((r) => r.kind === "three_accounts") ?? null;
  const liquidity = (liqRes.data ?? []) as Liquidity[];
  const err = sumRes.error?.message ?? liqRes.error?.message ?? settingsRes.error?.message;

  const enoughData = (total?.data_days ?? 0) >= days - 0.05;
  const costKnown = total?.cost_usd != null;
  const profit = total?.profit_usd_as_is ?? null;
  const verdict = !total ? "Sem dados ainda"
    : !enoughData ? "Dados insuficientes"
    : (profit ?? 0) > 0 ? "Compensa" : "Não compensa";

  return (
    <Shell email={email}>
      <PageHeader title="Compensa?" subtitle={`O farm paga a energia? Últimos ${days} dias, contando a partir do primeiro preço do Mercado.`} />
      <ErrorNote message={err} />
      <div className="stack">
      <Explain>
        <p>Renda = gemas dos drops por mês × (1 − 15% de comissão) × US$ 0,009 por gema (saque).</p>
        <p>Supõe vender tudo pela média de 7 dias do Mercado. O ouro não sai do jogo e não entra na renda.</p>
      </Explain>

      <section className="card stack verdict">
        <div className="spread">
          <h2 style={{ margin: 0 }}>{verdict}</h2>
          <span className="muted small">{total ? `${num(total.data_days)} de ${days} dias de dado` : ""}</span>
        </div>
        {total && (
          <>
            <p style={{ margin: 0 }}>
              Lucro projetado (como está): <strong>{usd(profit)}</strong> por mês
              {" · "}com o worker 24 h/dia: <strong>{usd(total.profit_usd_24h)}</strong>
            </p>
            {!costKnown && <p className="small error" style={{ margin: 0 }}>Custo de energia não informado: o lucro está sem ele.</p>}
            {!enoughData && <p className="small muted" style={{ margin: 0 }}>Com menos de {days} dias de dado, a projeção ainda é fraca.</p>}
            <div className="stats">
              <Stat label="Gemas por dia" value={num(total.gems_per_day)} />
              <Stat label="Gemas no mês (como está)" value={num(total.month_gems_as_is)} />
              <Stat label="Renda (como está)" value={usd(total.income_usd_as_is)} />
              <Stat label="Custo de energia" value={costKnown ? usd(total.cost_usd) : "não informado"} />
              <Stat label="Gemas no mês (24 h/dia)" value={num(total.month_gems_24h)} />
              <Stat label="Renda (24 h/dia)" value={usd(total.income_usd_24h)} />
              {three && <Stat label="Lucro com 3 contas (como está)" value={usd(three.profit_usd_as_is)} />}
              {three && <Stat label="Lucro com 3 contas (24 h/dia)" value={usd(three.profit_usd_24h)} />}
            </div>
          </>
        )}
      </section>

      {potential && (
        <div>
          <p className="muted small" style={{ margin: "0 0 .5rem" }}>
            Potencial: o que a conta renderia no foco gemas, nas melhores hunts que ela alcança (a renda acima é a do
            foco atual).
          </p>
          <GemsCard plan={null} potential={potential} />
        </div>
      )}

      {accounts.length > 0 && (
        <Panel title="Por conta" flush>
          <table>
            <thead>
              <tr>
                <th>Conta</th><th>Dias de dado</th><th>Horas ativas</th><th>Gemas</th><th>Gemas/dia</th>
                <th>Gemas/h ativa</th><th>Renda/mês (como está)</th><th>Renda/mês (24 h)</th><th>Ouro dos drops</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
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

      {liquidity.length > 0 && (
        <Panel title="Liquidez" meta="dropado contra vendido por semana" flush>
          <table>
            <thead><tr><th>Item</th><th>Dropado/semana</th><th>Vendido/semana</th><th>Parcela</th></tr></thead>
            <tbody>
              {liquidity.map((l) => (
                <tr key={l.name}>
                  <td>{l.name}</td>
                  <td>{num(l.dropped_week)}</td>
                  <td>{l.sold_week == null ? "sem vendas" : num(l.sold_week)}</td>
                  <td className={l.flagged ? "error" : ""}>{l.share == null ? "—" : `${num(l.share * 100)}%`}{l.flagged ? " · otimista" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="panel-note">Acima de 10% do vendido por semana, vender tudo pela média é otimista.</p>
        </Panel>
      )}

      <SettingsForm initial={settings} />
      </div>
    </Shell>
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
