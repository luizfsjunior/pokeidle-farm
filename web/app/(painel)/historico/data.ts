import type { SupabaseClient } from "@supabase/supabase-js";

export const PERIODS = { "7": "7 dias", "30": "30 dias", "90": "90 dias" } as const;
export type Period = keyof typeof PERIODS;

/** Uma linha da função `account_history` (supabase/migrations/20261127200000_historico.sql). */
export type Day = {
  account_id: string;
  day: string;
  kills: number; xp: number; gold: number; gold_net: number; consumables_gold: number;
  captures: number; capture_attempts: number; shinies: number; active_minutes: number;
  disconnects: number; pokecenter: number; drops_value_orb: number;
  level: number | null; trainer_xp: number | null; gems: number | null; diamonds: number | null;
  dex_caught: number | null; pokemon_count: number | null;
};

const NUMERIC = ["kills", "xp", "gold", "gold_net", "consumables_gold", "captures", "capture_attempts", "shinies",
  "active_minutes", "disconnects", "pokecenter", "drops_value_orb"] as const;
const NULLABLE = ["level", "trainer_xp", "gems", "diamonds", "dex_caught", "pokemon_count"] as const;

/** Resumo de uma conta no período (a tabela do topo). */
export type Summary = {
  days: Day[];
  xp: number; kills: number; goldNet: number; consumables: number; captures: number; attempts: number; shinies: number;
  minutes: number; disconnects: number; gemsDrops: number;
  levelFrom: number | null; levelTo: number | null; gemsFrom: number | null; gemsTo: number | null;
  dexFrom: number | null; dexTo: number | null;
};

const first = <T,>(xs: (T | null)[]) => xs.find((x) => x != null) ?? null;
const last = <T,>(xs: (T | null)[]) => first([...xs].reverse());

export function summarize(days: Day[]): Summary {
  const s = (k: (typeof NUMERIC)[number]) => days.reduce((t, d) => t + d[k], 0);
  return {
    days,
    xp: s("xp"), kills: s("kills"), goldNet: s("gold_net"), consumables: s("consumables_gold"), captures: s("captures"),
    attempts: s("capture_attempts"), shinies: s("shinies"), minutes: s("active_minutes"), disconnects: s("disconnects"),
    gemsDrops: s("drops_value_orb"),
    levelFrom: first(days.map((d) => d.level)), levelTo: last(days.map((d) => d.level)),
    gemsFrom: first(days.map((d) => d.gems)), gemsTo: last(days.map((d) => d.gems)),
    dexFrom: first(days.map((d) => d.dex_caught)), dexTo: last(days.map((d) => d.dex_caught)),
  };
}

/** Os dias do período por conta, já com números (o PostgREST manda numeric como texto). */
export async function loadHistory(supabase: SupabaseClient, period: Period): Promise<Map<string, Summary>> {
  const { data, error } = await supabase.rpc("account_history", { p_days: Number(period) });
  if (error) throw new Error(error.message);
  const by = new Map<string, Day[]>();
  for (const r of (data ?? []) as Record<string, unknown>[]) {
    const d = { account_id: r.account_id as string, day: r.day as string } as Day;
    for (const k of NUMERIC) d[k] = Number(r[k]) || 0;
    for (const k of NULLABLE) d[k] = r[k] == null ? null : Number(r[k]);
    const list = by.get(d.account_id) ?? [];
    list.push(d);
    by.set(d.account_id, list);
  }
  return new Map([...by].map(([id, days]) => [id, summarize(days)]));
}
