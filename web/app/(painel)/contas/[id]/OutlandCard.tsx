import { Bar, Hint } from "@/components/Page";
import { ago, num } from "@/lib/format";
import type { ProgressPlanData } from "./GemsCard";

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
  prices: Record<string, { gems: number | null; chance: number; tier_scaled: boolean }>;
  hunts: number;
  options: OutlandOption[];
};

const usdDay = (gemsPerHour: number) => gemsPerHour * 24 * 0.009; // a comissão já vem descontada
const money = (v: number) =>
  `US$ ${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)}`;
const hours1 = (h: number) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(h);
const fmtEta = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" });

/**
 * Card "Outland": o que a conta deve render em gemas quando chegar no 150. Substituiu o potencial em
 * pedras, que ficam a 2 gemas com filas de semanas.
 */
export function OutlandCard({ data, progress = null }: { data: OutlandPotentialData; progress?: ProgressPlanData | null }) {
  const best = data.options[0] ?? null;
  const missing = data.trainer_level != null ? Math.max(0, data.goal_level - data.trainer_level) : null;
  const maxGems = Math.max(0, ...data.options.map((o) => o.gems_per_hour));
  const priced = Object.entries(data.prices);
  return (
    <section className="card stack">
      <div className="spread">
        <div className="with-hint"><h2 style={{ margin: 0 }}>Outland</h2><Hint>
          Antes do 150 não há gema de verdade: as pedras ficam a 2 gemas com filas de semanas. Na Outland caem os fragmentos
          (Key, Shiny Stone, Bicycle; 1 em 200 mil abates cada, até ×{num(data.top_tier_mult)} nos tiers altos) e o Bronze
          Boss Token (0,05%). Abates/h previstos pelo simulador com {data.active_name ?? "o ativo"} no {data.goal_level};
          preço = mediana das vendas reais, menos 15% de comissão; US$ 0,009 por gema.
        </Hint></div>
        <span className="muted small">estimativa {ago(data.at)}</span>
      </div>

      <p className="small" style={{ margin: 0 }}>
        {missing === 0 ? (
          <strong>Liberada.</strong>
        ) : (
          <>
            <strong>Faltam {missing ?? "?"} níveis</strong>
            {progress && progress.stuck_at == null && progress.goal >= data.goal_level
              ? `, ~${hours1(progress.hours)} h de farm${progress.eta ? ` (previsão ${fmtEta(progress.eta)})` : ""}`
              : ""}.
          </>
        )}
        {best ? (
          <>
            {" "}Lá, na melhor hunt ({best.name ?? best.slug}): <strong>~{num(best.gems_per_hour, { compact: true })} gemas/h</strong>{" "}
            ({money(usdDay(best.gems_per_hour))}/dia), até ~{num(best.gems_per_hour_top, { compact: true })} gemas/h no tier mais
            alto ({money(usdDay(best.gems_per_hour_top))}/dia).
          </>
        ) : (
          " Ainda sem previsão de abates para a Outland."
        )}
      </p>

      {data.options.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Hunt</th><th>Abates/h</th><th>Itens/dia</th><th>Gemas/h (tier 1)</th><th>Tier alto</th></tr>
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

      <p className="muted small" style={{ margin: 0 }}>
        Preços (mediana das vendas):{" "}
        {priced.map(([name, p]) => `${name} ${p.gems == null ? "sem venda" : num(p.gems)}`).join(", ")}.
        Não conta shiny: não há shiny nas hunts da Outland.
      </p>
    </section>
  );
}
