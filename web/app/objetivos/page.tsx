import { GoalSummary } from "@/components/GoalCard";
import { Shell } from "@/components/Shell";
import { fetchProgress } from "@/lib/goals";
import { requireUser } from "@/lib/supabase/server";
import type { Account, Goal, MetricDef } from "@/lib/types";
import { GoalForm } from "./GoalForm";

export const dynamic = "force-dynamic";

export default async function GoalsPage() {
  const { supabase, email } = await requireUser();
  const since = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);

  const [goalsRes, defs, accounts, hunts] = await Promise.all([
    supabase.from("goals").select("*").neq("status", "archived").order("created_at", { ascending: false }),
    supabase.from("metric_definitions").select("key, label, unit, kind, numerator, denominator, scale, description, sort").order("sort"),
    supabase.from("accounts").select("id, nick, role, enabled, status").order("nick"),
    supabase.from("metric_daily").select("hunt_slug").eq("metric", "kills").gte("day", since),
  ]);
  const goals = (goalsRes.data ?? []) as Goal[];
  const metricDefs = (defs.data ?? []) as MetricDef[];
  const progress = await Promise.all(goals.map((g) => fetchProgress(supabase, g.id)));
  const huntList = [...new Set((hunts.data ?? []).map((h) => h.hunt_slug as string).filter(Boolean))].sort();

  return (
    <Shell email={email}>
      <h1>Objetivos</h1>
      {goalsRes.error && <p className="error">{goalsRes.error.message}</p>}
      <div className="stack">
        {goals.length === 0 && <p className="muted">Nenhum objetivo ainda.</p>}
        {goals.map((g, i) => (
          <GoalSummary key={g.id} goal={g} progress={progress[i]} metric={metricDefs.find((m) => m.key === g.metric)} />
        ))}
        <GoalForm accounts={(accounts.data ?? []) as Account[]} metrics={metricDefs.filter((m) => m.kind === "base")} hunts={huntList} />
        <p className="muted small">
          Ritmo e previsão usam as últimas 24 h de relógio, contando o tempo parado. Para captura, a chance de cada
          pokémon bater o filtro vem das capturas dos últimos 7 dias (shiny usa 1 em 24.000). As fotos do progresso
          são tiradas de hora em hora.
        </p>
      </div>
    </Shell>
  );
}
