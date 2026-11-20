import type { SupabaseClient } from "@supabase/supabase-js";
import type { HuntHold, HuntOption } from "@/components/HuntPicker";
import { loadAlerts } from "@/lib/alerts";
import { loadActiveCapture } from "@/lib/capture";
import { loadAllHunts } from "@/lib/catalog";
import { loadProfiles, speciesOf } from "@/lib/profile";
import { rankSummary } from "@/lib/rank";
import { speciesLooktypes } from "@/lib/sprites";
import type { Account, Command } from "@/lib/types";
import type { GemsPlanData, ProgressPlanData } from "./PlanCard";
import type { OutlandPotentialData } from "./OutlandCard";
import type { ItemInfo } from "./ProfileSections";

export type PluginRow = { plugin: string; enabled: boolean; config: Record<string, unknown> };
type Daily = { day: string; level: number | null; xp: number | null; gold: number | null;
  gems: number | null; diamonds: number | null; pokemon_count: number | null; dex_caught: number | null };

const lastEvent = (supabase: SupabaseClient, id: string, type: string) =>
  supabase.from("events").select("received_at, data").eq("account_id", id).eq("type", type)
    .order("received_at", { ascending: false }).limit(1).maybeSingle();
const withAt = <T,>(r: { data: { received_at: unknown; data: unknown } | null }) =>
  r.data ? ({ at: r.data.received_at as string, ...(r.data.data as object) } as T) : null;

/** Tudo da página da conta numa ida só (as consultas que não dependem umas das outras vão juntas). */
export async function loadAccount(supabase: SupabaseClient, id: string) {
  const [accountRes, configs, cmds, profiles, potentialRes, huntsRes, capture, dailyRes, alerts] = await Promise.all([
    supabase.from("accounts").select("id, nick, role, enabled, status").eq("id", id).maybeSingle<Account>(),
    supabase.from("strategy_configs").select("plugin, enabled, config").eq("account_id", id).order("plugin"),
    supabase.from("commands").select("*").eq("account_id", id).order("created_at", { ascending: false }).limit(20),
    loadProfiles(supabase, [id]),
    lastEvent(supabase, id, "outland.potential"),
    loadAllHunts<HuntOption>(supabase, "slug, name, level"),
    loadActiveCapture(supabase, id),
    supabase.from("account_profile_daily").select("day, level, xp, gold, gems, diamonds, pokemon_count, dex_caught")
      .eq("account_id", id).order("day", { ascending: true }).limit(90),
    loadAlerts(supabase, [id]),
  ]);
  const account = accountRes.data;
  if (!account) return null;
  const plugins = (configs.data ?? []) as PluginRow[];
  const profile = profiles.get(id) ?? null;
  const rankOn = plugins.some((p) => p.plugin === "rank" && p.enabled);
  const gemsOn = plugins.some((p) => p.plugin === "gems" && p.enabled);
  const itemIds = profile ? Object.keys(profile.items).map(Number).filter(Number.isFinite) : [];

  const [rank, gemsPlanRes, progressRes, looktypes, itemsRes] = await Promise.all([
    rankOn ? rankSummary(supabase, id) : Promise.resolve(null),
    gemsOn ? lastEvent(supabase, id, "gems.plan") : Promise.resolve({ data: null }),
    lastEvent(supabase, id, "progress.plan"),
    profile ? speciesLooktypes(supabase, speciesOf(profile.team, profile.top_pokemon, profile.shinies)) : Promise.resolve(new Map<number, number>()),
    itemIds.length ? supabase.from("game_items").select("item_id, name, category, icon").in("item_id", itemIds) : Promise.resolve({ data: [] }),
  ]);
  const items = new Map<string, ItemInfo>(
    ((itemsRes.data ?? []) as { item_id: number; name: string; category: string | null; icon: string | null }[])
      .map((r) => [String(r.item_id), { name: r.name, category: r.category, icon: r.icon }]),
  );
  const holdCfg = plugins.find((p) => p.plugin === "hunt_hold");
  const hold: HuntHold = holdCfg?.enabled && typeof holdCfg.config.slug === "string" && typeof holdCfg.config.until === "string"
    ? { slug: holdCfg.config.slug, until: holdCfg.config.until } : null;

  return {
    account, plugins, profile, looktypes, items, rank, capture, hold,
    alerts: alerts.get(id) ?? [],
    commands: (cmds.data ?? []) as Command[],
    huntOptions: huntsRes.data,
    daily: (dailyRes.data ?? []) as Daily[],
    gemsPlan: withAt<GemsPlanData>(gemsPlanRes),
    outland: withAt<OutlandPotentialData>(potentialRes),
    progress: withAt<ProgressPlanData>(progressRes),
  };
}
