import { Bar, Hint } from "@/components/Page";
import { ago, dateTime, hours1, num } from "@/lib/format";

type Stone = { name: string; chance: number; gems: number | null; sold_week: number | null; per_week: number; counted_week: number };
export type GemOption = {
  slug: string;
  name: string | null;
  level: number;
  kills_per_hour: number;
  kph_source: "measured" | "measured_season" | "model" | "level" | "near_level" | "default";
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
  degraded?: string[]; // o plano "sem_catalogo" vem sem
  /** Foco XP: buscando a pedra da próxima evolução (docs/design/foco-xp-pedra.md). */
  stone_hunt?: StoneHunt | null;
};
export type StoneHunt = {
  stone: string; evolve_level: number; active_level: number | null; hunt: string; name: string | null;
  chance: number; stones_per_hour: number; hours_expected: number;
};
export type ProgressPhase = {
  from_level: number; to_level: number; hunt: string; species_id: number; species: string | null; hours: number;
  kills_per_hour: number; xp_per_hour: number; potions_per_hour: number; net_gold_per_hour: number;
  stone?: string | null; // fase de busca da pedra de evolução
};
/** Evento `progress.plan` (docs/design/simulador-2-progressao.md): plano até o marco no foco XP. */
export type ProgressPlanData = {
  at: string; goal: number; hours: number; eta?: string; stuck_at: number | null; trainer_level: number;
  phases: ProgressPhase[];
  evolutions: { level: number; to: number; to_name?: string | null; stone: string; farm_hours?: number }[];
};

const KPH_SOURCE: Record<GemOption["kph_source"], string> = {
  measured: "medido",
  measured_season: "medido, ajustado ao dia sazonal",
  model: "previsto (simulador)",
  level: "estimado pelo nível",
  near_level: "estimado (nível próximo)",
  default: "estimado (padrão)",
};
/**
 * Plano do foco XP (docs/design/foco-xp.md): a hunt de mais XP/h agora e o plano até o marco. O foco por pedras
 * saiu (docs/design/painel-ux-v2.md): conta ainda nele não mostra plano, o card "Fazendo agora" avisa.
 */
export function PlanCard({ plan, progress: raw = null }: { plan: GemsPlanData | null; progress?: ProgressPlanData | null }) {
  // conta que já passou do marco (ex.: nível 381 com marco 150): o plano até ele não diz mais nada
  const progress = raw && raw.trainer_level < raw.goal ? raw : null;
  if (plan?.objective === "xp") return <XpCard plan={plan} progress={progress} />;
  return progress ? <section className="card stack"><ProgressPlan progress={progress} /></section> : null;
}

/** Foco XP (docs/design/foco-xp.md): a hunt de mais XP/h e as melhores opções. */
function XpCard({ plan, progress }: { plan: GemsPlanData; progress: ProgressPlanData | null }) {
  const target = plan.target as unknown as XpOption | null;
  const options = (plan.options as unknown as XpOption[]) ?? [];
  const maxXp = Math.max(0, ...options.slice(0, 5).map((o) => o.xp_per_hour));
  return (
    <section className="card stack">
      <div className="spread">
        <div className="with-hint"><h2 style={{ margin: 0 }}>Plano de XP</h2><Hint>
          O ritmo é o medido na hunt, projetado para o nível do pokémon ativo; hunt nunca medida usa o simulador de combate.
          XP por abate: a medida, ou 0,6 × nível² + 8 com o bônus da conta. Passe o dedo nos números para ver a origem.
        </Hint></div>
        <span className="muted small">plano {ago(plan.at)}{plan.active_level ? ` · ativo nível ${plan.active_level}` : ""}</span>
      </div>
      <p className="small" style={{ margin: 0 }}>
        <strong>{plan.dry_run || !plan.acting ? "Ensaio" : "Ativo"}:</strong> {plan.current_hunt ?? "—"} → alvo{" "}
        {target ? `${target.name ?? target.slug} (~${num(target.xp_per_hour, { compact: true })} XP/h)` : "nenhum"}
        {(plan.degraded?.length ?? 0) > 0 && <span className="error"> · {plan.degraded?.join(", ")}</span>}
      </p>
      {plan.stone_hunt && (
        <p className="small" style={{ margin: 0 }}>
          <strong>Buscando {plan.stone_hunt.stone}</strong> para evoluir no {plan.stone_hunt.evolve_level}:{" "}
          {plan.stone_hunt.name ?? plan.stone_hunt.hunt}, ~{hours1(plan.stone_hunt.stones_per_hour)}{" "}
          por hora (~{hours1(plan.stone_hunt.hours_expected)} h para cair uma). Quando cair, evolui e volta para a hunt de XP.
        </p>
      )}
      <div className="table-scroll">
        <table>
          <thead><tr><th>Hunt</th><th>Nível</th><th>Abates/h</th><th>XP/abate</th><th>XP/h</th></tr></thead>
          <tbody>
            {options.slice(0, 5).map((o) => (
              <tr key={o.slug}>
                <td>{o.name ?? o.slug}</td>
                <td>{o.level}</td>
                <td title={KPH_SOURCE[o.kph_source]}>{num(o.kills_per_hour)}</td>
                <td title={o.xp_source === "measured" ? "medida" : "fórmula"}>{num(o.xp_per_kill)}</td>
                <td><Bar value={o.xp_per_hour} max={maxXp} tone="link" label={<strong>{num(o.xp_per_hour, { compact: true })}</strong>} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {progress && <ProgressPlan progress={progress} />}
    </section>
  );
}


/** Plano até o marco (camada 2 do simulador): fases, evoluções e previsão de chegada. */
function ProgressPlan({ progress }: { progress: ProgressPlanData }) {
  return (
    <div className="stack">
      <div className="spread">
        <div className="with-hint"><h3 style={{ margin: 0 }}>Até o nível {progress.goal}</h3><Hint>
          Simulação nível a nível: a melhor hunt que se paga em ouro (abates − poções), com os bônus de XP até expirarem e as
          evoluções. Sem a pedra, conta o tempo esperado numa hunt que a dropa. Não conta idas ao Centro.
        </Hint></div>
        <span className="muted small">plano {ago(progress.at)}</span>
      </div>
      <p className="small" style={{ margin: 0 }}>
        {progress.stuck_at != null ? (
          <span className="error">Travado no nível {progress.stuck_at}: nenhuma hunt se paga em ouro com o time atual.</span>
        ) : (
          <>
            <strong>~{hours1(progress.hours)} h</strong> de farm
            {progress.eta ? ` · previsão ${dateTime(progress.eta)}` : ""}
            {progress.evolutions.length > 0 &&
              ` · evolui ${progress.evolutions
                .map((e) => `${e.to_name ?? e.to} no ${e.level}${e.farm_hours ? ` (~${hours1(e.farm_hours)} h buscando ${e.stone})` : ""}`)
                .join(", ")}`}
          </>
        )}
      </p>
      {progress.stuck_at == null && progress.phases.length > 0 && <PhaseStrip progress={progress} />}
      <details className="more">
      <summary>Ver as fases</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th>Níveis</th><th>Hunt</th><th>Ativo</th><th>Horas</th><th>XP/h</th><th>Poções/h</th><th>Ouro/h</th></tr>
          </thead>
          <tbody>
            {progress.phases.map((p) => (
              <tr key={`${p.from_level}-${p.hunt}-${p.stone ?? ""}`}>
                <td>{p.from_level}–{p.to_level}</td>
                <td>{p.hunt}{p.stone ? <span className="muted"> · busca {p.stone}</span> : null}</td>
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
      </details>
    </div>
  );
}

/** As fases até o marco numa faixa: a largura é o tempo de cada uma. */
function PhaseStrip({ progress }: { progress: ProgressPlanData }) {
  const total = progress.phases.reduce((t, p) => t + p.hours, 0) || 1;
  const first = progress.phases[0];
  return (
    <div className="stack" style={{ gap: ".3rem" }}>
      <div className="phases" role="img" aria-label={`${progress.phases.length} fases até o nível ${progress.goal}`}>
        {progress.phases.map((p) => (
          <span key={`${p.from_level}-${p.hunt}-${p.stone ?? ""}`} style={{ flexGrow: (p.hours / total) * 100, flexBasis: 0 }}
            title={`${p.from_level}–${p.to_level}: ${p.hunt}, ${hours1(p.hours)} h`}>
            {p.hours / total > 0.12 ? p.hunt : ""}
          </span>
        ))}
      </div>
      <div className="phases-legend"><span>nível {first?.from_level}</span><span>{progress.goal}</span></div>
    </div>
  );
}
