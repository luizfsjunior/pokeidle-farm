import type { SupabaseClient } from "@supabase/supabase-js";
import type { CaptureFilter, GoalProgress } from "./types";

export async function fetchProgress(supabase: SupabaseClient, goalId: string): Promise<GoalProgress | null> {
  const { data } = await supabase.rpc("goal_progress", { p_goal: goalId });
  const row = Array.isArray(data) ? data[0] : data;
  if (!row) return null;
  const n = (v: unknown) => (v === null || v === undefined ? null : Number(v));
  return {
    goal_id: row.goal_id,
    current: Number(row.current),
    target: Number(row.target),
    pct: n(row.pct),
    rate_per_hour: n(row.rate_per_hour),
    p_match: n(row.p_match),
    eta: row.eta,
    on_track: row.on_track,
    chance_by_deadline: n(row.chance_by_deadline),
  };
}

export function describeFilter(f: CaptureFilter): string {
  const parts: string[] = [];
  if (f.species?.length) parts.push(f.species.join(" ou "));
  if (f.shiny === true) parts.push("shiny");
  if (f.shiny === false) parts.push("não shiny");
  if (f.min_quality !== undefined) parts.push(`qualidade ≥ ${f.min_quality}`);
  if (f.min_potency !== undefined) parts.push(`potência ≥ ${f.min_potency}`);
  if (f.min_iv_sum !== undefined) parts.push(`IV total ≥ ${f.min_iv_sum}`);
  for (const [k, v] of Object.entries(f.min_ivs ?? {})) parts.push(`${k.toUpperCase()} ≥ ${v}`);
  return parts.length ? parts.join(", ") : "qualquer pokémon";
}
