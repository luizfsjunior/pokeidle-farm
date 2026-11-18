"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { GoalSummary } from "@/components/GoalCard";
import { LdBlock } from "@/components/Loading";
import { ErrorNote, Fold, PageHeader } from "@/components/Page";
import { fetchProgress } from "@/lib/goals";
import { usePanel } from "@/lib/query/hooks";
import type { Account, Goal, MetricDef } from "@/lib/types";
import { GoalForm } from "./GoalForm";

async function loadGoals(supabase: SupabaseClient) {
  const since = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);
  const [goalsRes, defs, accounts, hunts] = await Promise.all([
    supabase.from("goals").select("*").neq("status", "archived").order("created_at", { ascending: false }),
    supabase.from("metric_definitions").select("key, label, unit, kind, numerator, denominator, scale, description, sort").order("sort"),
    supabase.from("accounts").select("id, nick, role, enabled, status").order("nick"),
    supabase.from("metric_daily").select("hunt_slug").eq("metric", "kills").gte("day", since),
  ]);
  const goals = (goalsRes.data ?? []) as Goal[];
  return {
    goals,
    progress: await Promise.all(goals.map((g) => fetchProgress(supabase, g.id))),
    metricDefs: (defs.data ?? []) as MetricDef[],
    accounts: (accounts.data ?? []) as Account[],
    hunts: [...new Set((hunts.data ?? []).map((h) => h.hunt_slug as string).filter(Boolean))].sort(),
    err: goalsRes.error?.message ?? null,
  };
}

/** Estática: os dados vêm no navegador, com cache (lib/query). */
export default function GoalsPage() {
  const { data: d } = usePanel(["goals"], loadGoals, { staleTime: 0 });
  return (
    <>
      <PageHeader title="Objetivos" hint={<>Ritmo e previsão usam as últimas 24 h, contando o tempo parado. Na captura, a chance de
        um pokémon bater o filtro vem das capturas dos últimos 7 dias. O progresso é fotografado de hora em hora.</>} />
      <ErrorNote message={d?.err} />
      <div className="stack">
        {!d && <><LdBlock h={150} /><LdBlock h={150} /></>}
        {d && (
          <Fold title="Novo objetivo" open={d.goals.length === 0}>
            <GoalForm accounts={d.accounts} metrics={d.metricDefs.filter((m) => m.kind === "base")} hunts={d.hunts} />
          </Fold>
        )}
        {d?.goals.map((g, i) => (
          <GoalSummary key={g.id} goal={g} progress={d.progress[i]} metric={d.metricDefs.find((m) => m.key === g.metric)} />
        ))}
      </div>
    </>
  );
}
