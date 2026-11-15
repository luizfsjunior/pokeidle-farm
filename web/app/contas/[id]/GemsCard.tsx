import { ago, num } from "@/lib/format";

type Stone = { name: string; chance: number; gems: number | null; sold_week: number | null; per_week: number; counted_week: number };
export type GemOption = {
  slug: string;
  name: string | null;
  level: number;
  kills_per_hour: number;
  kph_source: "measured" | "level" | "near_level" | "default";
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
export type GemsPotentialData = { at: string; trainer_level: number; prices: number; options: GemOption[] };

const KPH_SOURCE: Record<GemOption["kph_source"], string> = {
  measured: "medido",
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
export function GemsCard({ plan, potential }: { plan: GemsPlanData | null; potential: GemsPotentialData | null }) {
  if (plan?.objective === "xp") return <XpCard plan={plan} />;
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
function XpCard({ plan }: { plan: GemsPlanData }) {
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
        O ritmo é projetado para o nível atual do pokémon ativo (o dano cresce com o nível); a XP por abate é a medida na
        hunt, ou 0,6 × nível² + 8 com o bônus da conta.
      </p>
    </section>
  );
}
