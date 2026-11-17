import type { SupabaseClient } from "@supabase/supabase-js";
import { loadProfiles, speciesOf, type Profile } from "@/lib/profile";
import { rankLine } from "@/lib/rank";
import { speciesLooktypes } from "@/lib/sprites";
import { todaySP } from "@/lib/format";
import type { Account } from "@/lib/types";

export const TODAY_METRICS = [
  "kills", "xp", "gold", "gold_net", "captures", "capture_attempts", "active_minutes",
  "drops_value_orb", "drops_value_gold",
] as const;
export type Totals = Record<(typeof TODAY_METRICS)[number], number>;

export type Overview = {
  accounts: Account[];
  profiles: Map<string, Profile>;
  looktypes: Map<number, number>;
  lastSeen: Map<string, string>;
  ranks: Map<string, { species: number | null; target: string | null }>;
  totals: Map<string, Totals>;
  err: string | null;
};

/** Visão geral: contas, perfil, números de hoje e o rank de cada uma. */
export async function loadOverview(supabase: SupabaseClient): Promise<Overview> {
  const today = todaySP();
  const [accountsRes, dailyRes, rankRes] = await Promise.all([
    supabase.from("accounts").select("id, nick, role, enabled, status").order("role").order("nick"),
    supabase.from("metric_daily").select("account_id, metric, value").eq("day", today).in("metric", [...TODAY_METRICS]),
    supabase.from("strategy_configs").select("account_id").eq("plugin", "rank").eq("enabled", true),
  ]);
  const accounts = (accountsRes.data ?? []) as Account[];
  const rankOn = new Set((rankRes.data ?? []).map((r) => r.account_id as string));
  const lastSeen = new Map<string, string>();
  const ranks = new Map<string, { species: number | null; target: string | null }>();

  const [profiles] = await Promise.all([
    loadProfiles(supabase, accounts.map((a) => a.id)),
    ...accounts.map(async (a) => {
      if (rankOn.has(a.id)) ranks.set(a.id, await rankLine(supabase, a.id));
      const { data } = await supabase
        .from("events").select("received_at").eq("account_id", a.id)
        .order("received_at", { ascending: false }).limit(1).maybeSingle();
      if (data) lastSeen.set(a.id, data.received_at as string);
    }),
  ]);
  const looktypes = await speciesLooktypes(supabase, speciesOf(...[...profiles.values()].map((p) => p.team)));

  const totals = new Map<string, Totals>();
  for (const r of dailyRes.data ?? []) {
    const t = totals.get(r.account_id) ?? (Object.fromEntries(TODAY_METRICS.map((m) => [m, 0])) as Totals);
    t[r.metric as keyof Totals] += Number(r.value);
    totals.set(r.account_id, t);
  }
  return {
    accounts, profiles, looktypes, lastSeen, ranks, totals,
    err: accountsRes.error?.message ?? dailyRes.error?.message ?? null,
  };
}
