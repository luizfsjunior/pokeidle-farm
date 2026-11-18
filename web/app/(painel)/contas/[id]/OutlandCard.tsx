import { Bar, Hint } from "@/components/Page";
import { ago, dateTime, hours1, num } from "@/lib/format";
import { usd, USD_PER_ORB } from "@/lib/money";
import type { ProgressPlanData } from "./PlanCard";

export type OutlandOption = {
  slug: string; name: string | null; level: number; kills_per_hour: number;
  gems_per_hour: number; gems_per_hour_top: number; drops_per_day: number;
};
/** Evento `outland.potential` (docs/design/outland-potencial.md). */
export type OutlandPotentialData = {
  at: string;
  trainer_level: number | null;
  goal_level: number;
  active_species_id: number | null;
  active_name: string | null;
  top_tier_mult: number;
  top_tier_label?: string | null;
  prices: Record<string, { gems: number | null; chance: number; tier_scaled: boolean }>;
  hunts: number;
  options: OutlandOption[];
};

// as gemas do evento já vêm sem a comissão (worker/src/pokeidle_farm/outland_model.py)
const usdDay = (gemsPerHour: number) => usd(gemsPerHour * 24 * USD_PER_ORB);

/**
 * Card "Outland": o que a conta deve render em gemas quando chegar no 150. Substituiu o potencial em
 * pedras, que ficam a 2 gemas com filas de semanas.
 */
export function OutlandCard({ data, progress = null }: { data: OutlandPotentialData; progress?: ProgressPlanData | null }) {
  const best = data.options[0] ?? null;
  // evento de versão antiga pode vir sem os níveis: sem eles, não diz quanto falta (antes saía "NaN")
  const missing = typeof data.trainer_level === "number" && typeof data.goal_level === "number"
    ? Math.max(0, data.goal_level - data.trainer_level) : null;
  const maxGems = Math.max(0, ...data.options.map((o) => o.gems_per_hour));
  const priced = Object.entries(data.prices);
  return (
    <section className="card stack">
      <div className="spread">
        <div className="with-hint"><h2 style={{ margin: 0 }}>Outland</h2><Hint>
          Antes do 150 não há gema de verdade: as pedras ficam a 2 gemas com filas de semanas. Na Outland caem os fragmentos
          (Key, Shiny Stone e Bicycle, 1 em 250 mil abates cada) e o Bronze Boss Token (1 em 10 mil). O tier da Outland
          multiplica esses drops e sobe com o nível do treinador: ×1 até o 499, ×1,1 no 500, ×2 no 2.250. O selvagem é o
          mesmo em todos. Abates/h previstos pelo simulador com {data.active_name ?? "o ativo"} no {data.goal_level};
          preço = mediana das vendas reais, menos 15% de comissão; US$ 0,009 por gema. Não conta shiny: não há shiny nas
          hunts da Outland.
        </Hint></div>
        <span className="muted small">estimativa {ago(data.at)}</span>
      </div>

      <p className="small" style={{ margin: 0 }}>
        {missing === 0 ? (
          <strong>Liberada.</strong>
        ) : missing == null ? null : (
          <>
            <strong>Faltam {num(missing)} níveis</strong>
            {progress && progress.stuck_at == null && progress.goal >= data.goal_level
              ? `, ~${hours1(progress.hours)} h de farm${progress.eta ? ` (previsão ${dateTime(progress.eta)})` : ""}`
              : ""}.
          </>
        )}
        {best ? (
          <>
            {" "}Lá, na melhor hunt ({best.name ?? best.slug}): <strong>~{num(best.gems_per_hour, { compact: true })} gemas/h</strong>{" "}
            ({usdDay(best.gems_per_hour)}/dia)
            {data.top_tier_mult > 1
              ? `; no seu tier (${data.top_tier_label ?? "atual"}, ×${num(data.top_tier_mult)}), ~${num(best.gems_per_hour_top, { compact: true })} gemas/h (${usdDay(best.gems_per_hour_top)}/dia)`
              : ""}.
          </>
        ) : (
          " Ainda sem previsão de abates para a Outland."
        )}
      </p>

      {data.options.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Hunt</th><th>Abates/h</th><th>Itens/dia</th><th>Gemas/h (Outland 1)</th><th>No seu tier</th></tr>
            </thead>
            <tbody>
              {data.options.map((o) => (
                <tr key={o.slug}>
                  <td>{o.name ?? o.slug}</td>
                  <td>{num(o.kills_per_hour)}</td>
                  <td>{hours1(o.drops_per_day)}</td>
                  <td><Bar value={o.gems_per_hour} max={maxGems} tone="gem" label={num(o.gems_per_hour)} /></td>
                  <td>{num(o.gems_per_hour_top)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="chips">
        {priced.map(([name, p]) => (
          <span key={name} className="chip" title="Mediana das vendas, em gemas">{name} <strong>{p.gems == null ? "—" : num(p.gems)}</strong></span>
        ))}
      </div>
    </section>
  );
}
