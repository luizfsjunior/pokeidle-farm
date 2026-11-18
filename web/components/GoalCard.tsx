import Link from "next/link";
import { chance, dateTime, num } from "@/lib/format";
import { describeFilter } from "@/lib/goals";
import type { Goal, GoalProgress, MetricDef } from "@/lib/types";

/**
 * Cartão de um objetivo (docs/design/painel-ux-v2.md): o progresso grande, a previsão ao lado e o resto numa
 * linha. Os números por foto ficam na página do objetivo.
 */
export function GoalSummary({ goal, progress, metric, link = true }: { goal: Goal; progress: GoalProgress | null; metric?: MetricDef; link?: boolean }) {
  const unit = goal.kind === "capture" ? "pokémon" : metric?.unit ?? "";
  const pctVal = Math.min(100, progress?.pct ?? 0);
  const done = progress != null && progress.current >= goal.target;
  const title = link ? <Link href={`/objetivos/${goal.id}`}>{goal.name}</Link> : goal.name;
  const status = goal.status !== "active"
    ? <span className="badge">{goal.status === "done" ? "concluído" : "arquivado"}</span>
    : done ? <span className="badge ready">batido</span>
    : progress?.on_track == null ? null
    : progress.on_track ? <span className="badge ready">no ritmo</span> : <span className="badge needs_login">atrasado</span>;
  const rate = progress?.rate_per_hour
    ? progress.rate_per_hour < 1 ? `${num(progress.rate_per_hour * 24, { compact: true })}/dia` : `${num(progress.rate_per_hour, { compact: true })}/h`
    : null;

  return (
    <section className="card goal-card">
      <div className="spread">
        <h2 style={{ margin: 0 }}>{title}</h2>
        {status}
      </div>
      <div className="goal-main">
        <div className="goal-pct num">{num(Math.round(pctVal))}%</div>
        <div className="goal-track">
          <div className="progress" aria-hidden><span style={{ width: `${pctVal}%` }} /></div>
          <div className="small secondary num">
            {num(progress?.current, { compact: true })} de {num(goal.target, { compact: true })} {unit}
          </div>
        </div>
        <div className="goal-eta">
          <span className="small muted">previsão</span>
          <strong className="small">{done ? "batido" : etaText(progress?.eta)}</strong>
        </div>
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        {goal.kind === "capture" ? describeFilter(goal.filter) : metric?.label ?? goal.metric}
        {goal.hunt_slug && ` · ${goal.hunt_slug}`}
        {rate && ` · ${rate}`}
        {goal.deadline && ` · prazo ${dateTime(goal.deadline)}`}
        {goal.kind === "capture" && goal.deadline && progress?.chance_by_deadline != null && ` · chance ${chance(progress.chance_by_deadline)}`}
      </p>
    </section>
  );
}

/** Previsão para mais de 5 anos é ruído do ritmo baixo, não uma data útil. */
function etaText(eta: string | null | undefined): string {
  if (!eta) return "sem ritmo ainda";
  return new Date(eta).getTime() - Date.now() > 5 * 365 * 86400_000 ? "ritmo baixo demais" : dateTime(eta);
}
