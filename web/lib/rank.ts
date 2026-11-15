import type { SupabaseClient } from "@supabase/supabase-js";
import { TZ } from "@/lib/format";

/**
 * Dados do foco rank lidos dos eventos (docs/design/fase-3b-metricas-e-card.md, seções 2 e 3).
 * Tudo da semana atual do Top Catch: desde domingo 00:00 de Brasília.
 */

export type QueueItem = { slug: string; species_id: number; hours: number; name?: string };

export type RankPosition = {
  position: number | null;
  inside: boolean;
  missing: number;
  cutoff: number | null;
  species: number;
};

export type RankSummary = {
  week: string; // "2026-11-15", como o jogo
  species: number | null; // espécies da semana pelo jogo
  position: RankPosition | null;
  plan: {
    at: string;
    reason: string;
    current: string | null;
    target: QueueItem | null;
    ballId: number | null;
    queueLen: number;
    queue: QueueItem[];
    skipped: number[];
    degraded: string[];
    dryRun: boolean;
  } | null;
  mode: { mode: string; at: string } | null;
  failures: { at: string; slug: string | null; reason: string | null }[];
  ratePerHour: number | null;
};

/** Domingo da semana atual em Brasília, no formato do jogo, e o instante em que ela começou. */
export function currentWeek(now = new Date()): { week: string; startIso: string; startDay: string } {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(now); // YYYY-MM-DD
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - d.getUTCDay()); // getUTCDay: 0 = domingo
  const week = d.toISOString().slice(0, 10);
  return { week, startIso: `${week}T00:00:00-03:00`, startDay: week };
}

type Row = { received_at: string; data: Record<string, unknown> };

/** Espécies da semana (o maior week_species do jogo) e o alvo do último plano: a linha da visão geral. */
export async function rankLine(supabase: SupabaseClient, accountId: string) {
  const { week, startIso } = currentWeek();
  const [species, plan] = await Promise.all([
    weekSpecies(supabase, accountId, week, startIso),
    lastEvent(supabase, accountId, "rank.plan", startIso),
  ]);
  const target = (plan?.data.target as QueueItem | null) ?? null;
  return { species, target: target?.slug ?? null };
}

export async function rankSummary(supabase: SupabaseClient, accountId: string): Promise<RankSummary> {
  const { week, startIso, startDay } = currentWeek();
  const dayAgo = new Date(Date.now() - 24 * 3600_000).toISOString();
  const [species, plan, mode, position, failures, daily] = await Promise.all([
    weekSpecies(supabase, accountId, week, startIso),
    lastEvent(supabase, accountId, "rank.plan", startIso),
    lastEvent(supabase, accountId, "rank.mode"),
    lastEvent(supabase, accountId, "rank.position", startIso),
    supabase.from("events").select("received_at, data").eq("account_id", accountId).eq("type", "rank.failed")
      .gte("received_at", dayAgo).order("received_at", { ascending: false }).limit(10),
    supabase.from("metric_daily").select("metric, value").eq("account_id", accountId)
      .gte("day", startDay).in("metric", ["rank_points", "active_minutes"]),
  ]);

  let points = 0;
  let minutes = 0;
  for (const r of daily.data ?? []) {
    if (r.metric === "rank_points") points += Number(r.value);
    else minutes += Number(r.value);
  }

  const p = plan?.data;
  const pos = position && position.data.week_start === week ? position.data : null;
  return {
    week,
    species,
    position: pos
      ? {
          position: (pos.position as number | null) ?? null,
          inside: pos.inside === true,
          missing: Number(pos.missing) || 0,
          cutoff: (pos.cutoff as number | null) ?? null,
          species: Number(pos.species) || 0,
        }
      : null,
    plan: plan && p
      ? {
          at: plan.received_at,
          reason: String(p.reason ?? ""),
          current: (p.current_hunt as string | null) ?? null,
          target: (p.target as QueueItem | null) ?? null,
          ballId: (p.ball_id as number | null) ?? null,
          queueLen: Number(p.queue_len) || 0,
          queue: Array.isArray(p.queue) ? (p.queue as QueueItem[]) : [],
          skipped: Array.isArray(p.skipped) ? (p.skipped as number[]) : [],
          degraded: Array.isArray(p.degraded) ? (p.degraded as string[]) : [],
          dryRun: p.dry_run !== false,
        }
      : null,
    mode: mode ? { mode: String(mode.data.mode ?? ""), at: mode.received_at } : null,
    failures: ((failures.data ?? []) as Row[]).map((f) => ({
      at: f.received_at,
      slug: (f.data.slug as string | null) ?? null,
      reason: (f.data.reason as string | null) ?? null,
    })),
    ratePerHour: minutes > 0 ? (points * 60) / minutes : null,
  };
}

async function weekSpecies(supabase: SupabaseClient, accountId: string, week: string, sinceIso: string) {
  const { data } = await supabase.from("events").select("data").eq("account_id", accountId)
    .in("type", ["rank.catch", "rank.week"]).gte("received_at", sinceIso)
    .order("received_at", { ascending: false }).limit(200);
  let best: number | null = null;
  for (const r of (data ?? []) as Pick<Row, "data">[]) {
    const n = r.data.week_species;
    if (r.data.week_start === week && typeof n === "number" && (best === null || n > best)) best = n;
  }
  return best;
}

async function lastEvent(supabase: SupabaseClient, accountId: string, type: string, sinceIso?: string) {
  let q = supabase.from("events").select("received_at, data").eq("account_id", accountId).eq("type", type);
  if (sinceIso) q = q.gte("received_at", sinceIso);
  const { data } = await q.order("received_at", { ascending: false }).limit(1).maybeSingle<Row>();
  return data ?? null;
}
