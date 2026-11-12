import { Shell } from "@/components/Shell";
import { requireUser } from "@/lib/supabase/server";
import type { Account, MetricDef } from "@/lib/types";
import { Explorer } from "./Explorer";

export const dynamic = "force-dynamic";

export default async function MetricsPage() {
  const { supabase, email } = await requireUser();
  const since = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10);

  const [defs, accounts, hunts] = await Promise.all([
    supabase.from("metric_definitions").select("key, label, unit, kind, numerator, denominator, scale, description, sort").order("sort"),
    supabase.from("accounts").select("id, nick, role, enabled, status").order("nick"),
    supabase.from("metric_daily").select("hunt_slug").eq("metric", "kills").gte("day", since),
  ]);
  const huntList = [...new Set((hunts.data ?? []).map((h) => h.hunt_slug as string).filter(Boolean))].sort();

  return (
    <Shell email={email}>
      <h1>Métricas</h1>
      {defs.error && <p className="error">Erro ao ler as métricas: {defs.error.message}</p>}
      <Explorer defs={(defs.data ?? []) as MetricDef[]} accounts={(accounts.data ?? []) as Account[]} hunts={huntList} />
    </Shell>
  );
}
