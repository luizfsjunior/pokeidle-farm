import { ago, num } from "@/lib/format";

type Stone = { name: string; chance: number; gems: number | null; sold_week: number | null; per_week: number; counted_week: number };
export type GemOption = {
  slug: string;
  name: string | null;
  level: number;
  kills_per_hour: number;
  kph_source: "measured" | "model" | "level" | "near_level" | "default";
  gems_per_hour: number;
  capped_gems_per_hour: number;
  stones: Stone[];
};
export type XpOption = {
  slug: string; name: string | null; level: number; kills_per_hour: number; kph_source: GemOption["kph_source"];
  xp_per_kill: number; xp_source: "measured" | "formula"; xp_per_hour: number;
};
export type GemsPlanData = {
  at: string;
  objective?: "gems" | "xp";
  active_level?: number | null;
  reason: string;
  dry_run: boolean;
  acting: boolean;
  current_hunt: string | null;
  target: GemOption | null;
  here: GemOption | null;
  options: GemOption[];
  month_gems_24h: number;
  degraded: string[];
};
export type ProgressPhase = {
  from_level: number; to_level: number; hunt: string; species_id: number; species: string | null; hours: number;
  kills_per_hour: number; xp_per_hour: number; potions_per_hour: number; net_gold_per_hour: number;
};
/** Evento `progress.plan` (docs/design/simulador-2-progressao.md): plano até o marco no foco XP. */
export type ProgressPlanData = {
  at: string; goal: number; hours: number; eta?: string; stuck_at: number | null; trainer_level: number;
  phases: ProgressPhase[]; evolutions: { level: number; to: number; to_name?: string | null; stone: string }[];
};
export type GemsPotentialData = { at: string; trainer_level: number; prices: number; options: GemOption[] };

const KPH_SOURCE: Record<GemOption["kph_source"], string> = {
  measured: "medido",
  model: "previsto (simulador)",
  level: "estimado pelo nível",
  near_level: "estimado (nível próximo)",
  default: "estimado (padrão)",
};
// gemas → US$: comissão de 15% e saque a US$ 0,009 (fase 8)
const usdMonth = (gemsPerHour: number) => gemsPerHour * 24 * 30 * 0.85 * 0.009;

/**
 * Card "Gemas" (docs/design/foco-gemas-e-ritmo.md): o que o foco gemas decidiu e, para qualquer foco,
 * o potencial das melhores hunts em pedras de evolução (calculado a cada snapshot de preços).
 */
export function GemsCard({
  plan,
  potential,
  progress = null,
}: {
  plan: GemsPlanData | null;
  potential: GemsPotentialData | null;
  progress?: ProgressPlanData | null;
}) {
  if (plan?.objective === "xp") return <XpCard plan={plan} progress={progress} />;
  if (!plan && !potential) return null;
  const list = plan?.options ?? potential?.options ?? [];
  return (
    <section className="card stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Gemas (pedras de evolução)</h2>
        <span className="muted small">{plan ? `plano ${ago(plan.at)}` : potential ? `potencial ${ago(potential.at)}` : ""}</span>
      </div>
      {plan && (
        <p className="small" style={{ margin: 0 }}>
          <strong>{plan.dry_run || !plan.acting ? "Ensaio" : "Ativo"}:</strong> {plan.current_hunt ?? "—"} → alvo{" "}
          {plan.target ? `${plan.target.name ?? plan.target.slug} (~${num(plan.target.capped_gems_per_hour)} gemas/h, ~US$ ${num(usdMonth(plan.target.capped_gems_per_hour))}/mês a 24 h)` : "nenhum"}
          {plan.degraded.length > 0 && <span className="error"> · {plan.degraded.join(", ")}</span>}
        </p>
      )}
      {list.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr><th>Hunt</th><th>Nível</th><th>Abates/h</th><th>Pedras</th><th>Gemas/h</th><th>US$/mês (24 h)</th></tr>
            </thead>
            <tbody>
              {list.slice(0, 5).map((o) => (
                <tr key={o.slug}>
                  <td>{o.name ?? o.slug}</td>
                  <td>{o.level}</td>
                  <td>{num(o.kills_per_hour)} <span className="muted small">{KPH_SOURCE[o.kph_source]}</span></td>
                  <td className="small">{o.stones.map((s) => `${s.name}${s.gems == null ? " (sem preço)" : ` ${num(s.gems)}`}`).join(", ")}</td>
                  <td>{num(o.capped_gems_per_hour)}{o.capped_gems_per_hour < o.gems_per_hour - 0.05 && <span className="muted small"> (sem teto {num(o.gems_per_hour)})</span>}</td>
                  <td>{num(usdMonth(o.capped_gems_per_hour))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        Chance de pedra por abate pela posição na cadeia evolutiva (0,2% / 0,35% / 0,5%, do código do jogo); cada pedra
        vale o menor entre a média de 7 dias e o menor anúncio aberto, e conta até 10% do que o Mercado vende dela por
        semana. US$ com 15% de comissão e saque a US$ 0,009 por gema.
      </p>
    </section>
  );
}

/** Foco XP (docs/design/foco-xp.md): a hunt de mais XP/h e as melhores opções. */
function XpCard({ plan, progress }: { plan: GemsPlanData; progress: ProgressPlanData | null }) {
  const target = plan.target as unknown as XpOption | null;
  const options = (plan.options as unknown as XpOption[]) ?? [];
  return (
    <section className="card stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Foco XP</h2>
        <span className="muted small">plano {ago(plan.at)}{plan.active_level ? ` · ativo nível ${plan.active_level}` : ""}</span>
      </div>
      <p className="small" style={{ margin: 0 }}>
        <strong>{plan.dry_run || !plan.acting ? "Ensaio" : "Ativo"}:</strong> {plan.current_hunt ?? "—"} → alvo{" "}
        {target ? `${target.name ?? target.slug} (~${num(target.xp_per_hour, { compact: true })} XP/h)` : "nenhum"}
        {plan.degraded.length > 0 && <span className="error"> · {plan.degraded.join(", ")}</span>}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead><tr><th>Hunt</th><th>Nível</th><th>Abates/h</th><th>XP/abate</th><th>XP/h</th></tr></thead>
          <tbody>
            {options.slice(0, 5).map((o) => (
              <tr key={o.slug}>
                <td>{o.name ?? o.slug}</td>
                <td>{o.level}</td>
                <td>{num(o.kills_per_hour)} <span className="muted small">{KPH_SOURCE[o.kph_source]}</span></td>
                <td>{num(o.xp_per_kill)} <span className="muted small">{o.xp_source === "measured" ? "medida" : "fórmula"}</span></td>
                <td><strong>{num(o.xp_per_hour, { compact: true })}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        O ritmo é o medido na hunt, projetado para o nível atual do pokémon ativo; hunt nunca medida usa a previsão do
        simulador de combate. A XP por abate é a medida na hunt, ou 0,6 × nível² + 8 com o bônus da conta.
      </p>
      {progress && <ProgressPlan progress={progress} />}
    </section>
  );
}

const hours1 = (h: number) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(h);
const fmtEta = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" });

/** Plano até o marco (camada 2 do simulador): fases, evoluções e previsão de chegada. */
function ProgressPlan({ progress }: { progress: ProgressPlanData }) {
  return (
    <div className="stack">
      <div className="spread">
        <h3 style={{ margin: 0 }}>Até o nível {progress.goal}</h3>
        <span className="muted small">plano {ago(progress.at)}</span>
      </div>
      <p className="small" style={{ margin: 0 }}>
        {progress.stuck_at != null ? (
          <span className="error">Travado no nível {progress.stuck_at}: nenhuma hunt se paga em ouro com o time atual.</span>
        ) : (
          <>
            <strong>~{hours1(progress.hours)} h</strong> de farm
            {progress.eta ? ` · previsão ${fmtEta(progress.eta)}` : ""}
            {progress.evolutions.length > 0 &&
              ` · evolui ${progress.evolutions.map((e) => `${e.to_name ?? e.to} no ${e.level}`).join(", ")}`}
          </>
        )}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr><th>Níveis</th><th>Hunt</th><th>Ativo</th><th>Horas</th><th>XP/h</th><th>Poções/h</th><th>Ouro/h</th></tr>
          </thead>
          <tbody>
            {progress.phases.map((p) => (
              <tr key={`${p.from_level}-${p.hunt}`}>
                <td>{p.from_level}–{p.to_level}</td>
                <td>{p.hunt}</td>
                <td>{p.species ?? p.species_id}</td>
                <td>{hours1(p.hours)}</td>
                <td>{num(p.xp_per_hour, { compact: true })}</td>
                <td>{num(p.potions_per_hour)}</td>
                <td>{num(p.net_gold_per_hour, { compact: true })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        Simulação nível a nível: a melhor hunt que se paga em ouro (abates − poções), com os bônus de XP até expirarem e
        as evoluções quando há pedra. Não conta idas ao Centro nem o tempo das trocas de hunt.
      </p>
    </div>
  );
}
