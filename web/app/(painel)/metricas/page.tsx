"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { LdBlock } from "@/components/Loading";
import { ErrorNote, PageHeader } from "@/components/Page";
import { usePanel } from "@/lib/query/hooks";
import type { Account, MetricDef } from "@/lib/types";
import { Explorer } from "./Explorer";

async function loadMetricOptions(supabase: SupabaseClient) {
  const since = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);
  const [defs, accounts, hunts] = await Promise.all([
    supabase.from("metric_definitions").select("key, label, unit, kind, numerator, denominator, scale, description, sort").order("sort"),
    supabase.from("accounts").select("id, nick, role, enabled, status").order("nick"),
    supabase.from("metric_daily").select("hunt_slug").eq("metric", "kills").gte("day", since),
  ]);
  return {
    defs: (defs.data ?? []) as MetricDef[],
    accounts: (accounts.data ?? []) as Account[],
    hunts: [...new Set((hunts.data ?? []).map((h) => h.hunt_slug as string).filter(Boolean))].sort(),
    err: defs.error?.message ?? null,
  };
}

/** Estática: as opções vêm no navegador, com cache; a série, o Explorer busca. */
export default function MetricsPage() {
  const { data: d } = usePanel(["metric-options"], loadMetricOptions, { staleTime: 5 * 60_000 });
  return (
    <>
      <PageHeader title="Métricas" />
      <ErrorNote message={d?.err} />
      {d ? <Explorer defs={d.defs} accounts={d.accounts} hunts={d.hunts} /> : <LdBlock h={420} />}
    </>
  );
}
