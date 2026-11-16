import type { SupabaseClient } from "@supabase/supabase-js";
import type { ActiveCapture } from "@/components/Capture";

/** A captura em andamento da conta (config do capture_target) e quantas já saíram desde o início. */
export async function loadActiveCapture(supabase: SupabaseClient, accountId: string): Promise<ActiveCapture | null> {
  const { data } = await supabase.from("strategy_configs").select("enabled, config")
    .eq("account_id", accountId).eq("plugin", "capture_target").maybeSingle();
  const cfg = (data?.config ?? null) as Omit<ActiveCapture, "captured"> | null;
  if (!data?.enabled || !cfg?.species_id || !cfg.started_at) return null;
  const { count } = await supabase.from("events").select("id", { count: "exact", head: true })
    .eq("account_id", accountId).eq("type", "pokemon.captured").gte("received_at", cfg.started_at)
    .eq("data->>species_id", String(cfg.species_id));
  return { ...cfg, captured: count ?? 0 };
}
