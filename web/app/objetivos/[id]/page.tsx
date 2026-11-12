import Link from "next/link";
import { notFound } from "next/navigation";
import { GoalSummary } from "@/components/GoalCard";
import { LineChart } from "@/components/LineChart";
import { Shell } from "@/components/Shell";
import { chance, dateTime, num } from "@/lib/format";
import { fetchProgress } from "@/lib/goals";
import { requireUser } from "@/lib/supabase/server";
import type { Goal, MetricDef, Snapshot } from "@/lib/types";
import { deleteGoal, setGoalStatus } from "../actions";

export const dynamic = "force-dynamic";

export default async function GoalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { supabase, email } = await requireUser();

  const { data: goal } = await supabase.from("goals").select("*").eq("id", id).maybeSingle<Goal>();
  if (!goal) notFound();

  const [progress, snaps, def] = await Promise.all([
    fetchProgress(supabase, id),
    supabase.from("goal_snapshots").select("taken_at, current, rate_per_hour, eta, chance_by_deadline")
      .eq("goal_id", id).order("taken_at", { ascending: true }).limit(2000),
    goal.metric
      ? supabase.from("metric_definitions").select("*").eq("key", goal.metric).maybeSingle<MetricDef>()
      : Promise.resolve({ data: null }),
  ]);
  const snapshots = (snaps.data ?? []) as Snapshot[];
  const unit = goal.kind === "capture" ? "pokémon" : def.data?.unit ?? "";

  return (
    <Shell email={email}>
      <p className="small"><Link href="/objetivos">← Objetivos</Link></p>
      <div className="stack">
        <GoalSummary goal={goal} progress={progress} metric={def.data ?? undefined} link={false} />

        <section className="card">
          <h2>Histórico do progresso</h2>
          {snapshots.length === 0 ? (
            <p className="muted">A primeira foto sai no próximo minuto 7 de alguma hora (job <code>goal-snapshots</code>).</p>
          ) : (
            <LineChart points={snapshots.map((s) => ({ t: s.taken_at, v: Number(s.current) }))} bucket="hour" unit={unit} label="Progresso" />
          )}
          {snapshots.length > 0 && (
            <details>
              <summary>Previsões anteriores</summary>
              <table>
                <thead><tr><th>Foto</th><th className="r">Atual</th><th className="r">Ritmo/h</th><th>Previsão</th>{goal.kind === "capture" && goal.deadline && <th className="r">Chance</th>}</tr></thead>
                <tbody>
                  {[...snapshots].reverse().slice(0, 200).map((s) => (
                    <tr key={s.taken_at}>
                      <td>{dateTime(s.taken_at)}</td>
                      <td className="r">{num(Number(s.current))}</td>
                      <td className="r">{num(s.rate_per_hour === null ? null : Number(s.rate_per_hour))}</td>
                      <td>{dateTime(s.eta)}</td>
                      {goal.kind === "capture" && goal.deadline && <td className="r">{chance(s.chance_by_deadline === null ? null : Number(s.chance_by_deadline))}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </section>

        <section className="card row">
          <form action={setGoalStatus}>
            <input type="hidden" name="id" value={goal.id} />
            <input type="hidden" name="status" value={goal.status === "archived" ? "active" : "archived"} />
            <button className="ghost" type="submit">{goal.status === "archived" ? "Reativar" : "Arquivar"}</button>
          </form>
          <form action={deleteGoal}>
            <input type="hidden" name="id" value={goal.id} />
            <button className="ghost" type="submit" style={{ color: "var(--critical)" }}>Excluir</button>
          </form>
          <span className="muted small">Criado em {dateTime(goal.created_at)} · conta desde {dateTime(goal.starts_at)}</span>
        </section>
      </div>
    </Shell>
  );
}
