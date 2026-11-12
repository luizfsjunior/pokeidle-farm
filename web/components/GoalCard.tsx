import Link from "next/link";
import { chance, dateTime, num } from "@/lib/format";
import { describeFilter } from "@/lib/goals";
import type { Goal, GoalProgress, MetricDef } from "@/lib/types";

export function GoalSummary({ goal, progress, metric, link = true }: { goal: Goal; progress: GoalProgress | null; metric?: MetricDef; link?: boolean }) {
  const unit = goal.kind === "capture" ? "pokémon" : metric?.unit ?? "";
  const pctVal = progress?.pct ?? 0;
  const title = link ? <Link href={`/objetivos/${goal.id}`}>{goal.name}</Link> : goal.name;
  const track =
    progress?.on_track === null || progress?.on_track === undefined ? null
      : progress.on_track ? <span className="badge ready">no ritmo</span> : <span className="badge needs_login">atrasado</span>;

  return (
    <section className="card">
      <div className="spread">
        <h2 style={{ margin: 0 }}>{title}</h2>
        <div className="row">
          {goal.status !== "active" && <span className="badge">{goal.status === "done" ? "concluído" : "arquivado"}</span>}
          {goal.status === "active" && track}
        </div>
      </div>
      <div className="muted small">
        {goal.kind === "capture" ? describeFilter(goal.filter) : metric?.label ?? goal.metric}
        {goal.hunt_slug && ` · hunt ${goal.hunt_slug}`}
        {goal.deadline && ` · prazo ${dateTime(goal.deadline)}`}
      </div>
      <div className="progress" aria-hidden><span style={{ width: `${Math.min(100, pctVal)}%` }} /></div>
      <div className="stats" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))" }}>
        <div className="stat"><div className="label">Progresso</div><div className="value">{num(progress?.current, { compact: true })} / {num(goal.target, { compact: true })} <span className="muted small">{unit}</span></div></div>
        <div className="stat"><div className="label">Ritmo (últimas 24 h)</div><div className="value">{progress?.rate_per_hour ? `${num(progress.rate_per_hour < 1 ? progress.rate_per_hour * 24 : progress.rate_per_hour, { compact: true })}/${progress.rate_per_hour < 1 ? "dia" : "h"}` : "—"}</div></div>
        <div className="stat"><div className="label">Previsão</div><div className="value">{progress && progress.current >= goal.target ? "batido" : dateTime(progress?.eta)}</div></div>
        {goal.kind === "capture" && <div className="stat"><div className="label">Captura que bate o filtro</div><div className="value">{chance(progress?.p_match)}</div></div>}
        {goal.kind === "capture" && goal.deadline && <div className="stat"><div className="label">Chance até o prazo</div><div className="value">{chance(progress?.chance_by_deadline)}</div></div>}
      </div>
    </section>
  );
}
