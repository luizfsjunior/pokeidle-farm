"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import Link from "next/link";
import { useParams } from "next/navigation";
import { GoalSummary } from "@/components/GoalCard";
import { LineChart } from "@/components/LineChart";
import { LdBlock } from "@/components/Loading";
import { PageHeader } from "@/components/Page";
import { chance, dateTime, num } from "@/lib/format";
import { fetchProgress } from "@/lib/goals";
import { usePanel, useRefreshAll } from "@/lib/query/hooks";
import type { Goal, MetricDef, Snapshot } from "@/lib/types";
import { deleteGoal, setGoalStatus } from "../actions";

async function loadGoal(supabase: SupabaseClient, id: string) {
  const { data: goal } = await supabase.from("goals").select("*").eq("id", id).maybeSingle<Goal>();
  if (!goal) return null;
  const [progress, snaps, def] = await Promise.all([
    fetchProgress(supabase, id),
    supabase.from("goal_snapshots").select("taken_at, current, rate_per_hour, eta, chance_by_deadline")
      .eq("goal_id", id).order("taken_at", { ascending: true }).limit(2000),
    goal.metric
      ? supabase.from("metric_definitions").select("*").eq("key", goal.metric).maybeSingle<MetricDef>()
      : Promise.resolve({ data: null }),
  ]);
  return { goal, progress, snapshots: (snaps.data ?? []) as Snapshot[], def: def.data ?? undefined };
}

/** Estática: os dados vêm no navegador, com cache (lib/query). */
export default function GoalPage() {
  const { id } = useParams<{ id: string }>();
  const q = usePanel(["goal", id], (sb) => loadGoal(sb, id), { staleTime: 0 });
  const refresh = useRefreshAll();
  const d = q.data;
  const goal = d?.goal;
  const unit = goal?.kind === "capture" ? "pokémon" : d?.def?.unit ?? "";

  return (
    <>
      <PageHeader title="Objetivo" subtitle={<Link href="/objetivos">← Todos os objetivos</Link>} />
      {q.isSuccess && !d && <p className="muted">Objetivo não encontrado.</p>}
      <div className="stack">
        {!q.isSuccess && <><LdBlock h={150} /><LdBlock h={280} /></>}
        {goal && d && (
          <>
            <GoalSummary goal={goal} progress={d.progress} metric={d.def} link={false} />

            <section className="card">
              <h2>Histórico do progresso</h2>
              {d.snapshots.length === 0 ? (
                <p className="muted">A primeira foto sai no próximo minuto 7 de alguma hora (job <code>goal-snapshots</code>).</p>
              ) : (
                <LineChart points={d.snapshots.map((s) => ({ t: s.taken_at, v: Number(s.current) }))} bucket="hour" unit={unit} label="Progresso" />
              )}
              {d.snapshots.length > 0 && (
                <details>
                  <summary>Previsões anteriores</summary>
                  <table>
                    <thead><tr><th>Foto</th><th className="r">Atual</th><th className="r">Ritmo/h</th><th>Previsão</th>{goal.kind === "capture" && goal.deadline && <th className="r">Chance</th>}</tr></thead>
                    <tbody>
                      {[...d.snapshots].reverse().slice(0, 200).map((s) => (
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
              <form action={async (fd) => { await setGoalStatus(fd); await refresh(); }}>
                <input type="hidden" name="id" value={goal.id} />
                <input type="hidden" name="status" value={goal.status === "archived" ? "active" : "archived"} />
                <button className="ghost" type="submit">{goal.status === "archived" ? "Reativar" : "Arquivar"}</button>
              </form>
              <form action={async (fd) => { await refresh(); await deleteGoal(fd); }}>
                <input type="hidden" name="id" value={goal.id} />
                <button className="ghost" type="submit" style={{ color: "var(--critical)" }}>Excluir</button>
              </form>
              <span className="muted small">Criado em {dateTime(goal.created_at)} · conta desde {dateTime(goal.starts_at)}</span>
            </section>
          </>
        )}
      </div>
    </>
  );
}
