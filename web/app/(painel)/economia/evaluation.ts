import type { SupabaseClient } from "@supabase/supabase-js";
import type { EvalSettings } from "./SettingsForm";

/** Linha de `evaluation_summary` (só as contas de farm; drops sem as pedras, docs/design/painel-ux-v2.md). */
export type EvalRow = {
  kind: "account" | "total" | "three_accounts";
  account_id: string | null;
  nick: string | null;
  gems: number | null;
  active_hours: number | null;
  data_days: number | null;
  gems_per_day: number | null;
  gems_per_hour: number | null;
  income_usd_as_is: number | null;
  income_usd_24h: number | null;
  cost_usd: number | null;
  profit_usd_as_is: number | null;
  profit_usd_24h: number | null;
};

const NO_SETTINGS: EvalSettings = {
  machine_watts: null, marginal: false, kwh_price_brl: null, usd_brl: null, fixed_cost_usd: null, window_days: 7,
};

/** "Compensa?" (docs/design/fase-8-compensa.md): renda dos drops contra o custo do mês. */
export async function loadEvaluation(supabase: SupabaseClient) {
  const settingsRes = await supabase.from("evaluation_settings")
    .select("machine_watts, marginal, kwh_price_brl, usd_brl, fixed_cost_usd, window_days").maybeSingle<EvalSettings>();
  const settings = settingsRes.data ?? NO_SETTINGS;
  const sumRes = await supabase.rpc("evaluation_summary", { p_days: settings.window_days });
  const rows = (sumRes.data ?? []) as EvalRow[];
  return {
    settings,
    accounts: rows.filter((r) => r.kind === "account"),
    total: rows.find((r) => r.kind === "total") ?? null,
    err: sumRes.error?.message ?? settingsRes.error?.message ?? null,
  };
}
