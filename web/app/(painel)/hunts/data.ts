import type { SupabaseClient } from "@supabase/supabase-js";
import { num } from "@/lib/format";
import {
  chainPosition, gemsPer1000, loadAllSpecies, loadLootStones, loadStonePrices, parentsOf, stonesOf,
  type CatalogHunt, type Stone,
} from "@/lib/hunts";
import { speciesLooktypes } from "@/lib/sprites";
import type { HuntDetail } from "./HuntDrawer";

export const PERIODS = { "1": "24 h", "7": "7 dias", "30": "30 dias" } as const;
export type Period = keyof typeof PERIODS;

export type Summary = {
  hunt_slug: string; kills: number; active_minutes: number; gold: number; gold_net: number; drops: number;
  drops_value_orb: number; drops_value_gold: number; capture_attempts: number; captures: number; shinies: number;
  rank_points: number; last_hour: string;
};
export type Reachable = { h: CatalogHunt; stones: Stone[]; g1000: number; kph: number | null; gemsHour: number | null };

/** Uma conta na sanfona: onde está agora e o que cada hunt rendeu para ela no período. */
export type AccountHunts = {
  id: string; nick: string; level: number | null; current: { slug: string; at: string } | null; visited: Summary[];
  totals: { minutes: number; kills: number; gems: number; goldNet: number; captures: number; shinies: number };
};

export const perHour = (v: number, mins: number) => (mins > 0 ? (v * 60) / mins : null);
export const stoneText = (stones: Stone[]) =>
  stones.length === 0
    ? "—"
    : stones
        .map((s) => {
          const label = s.name.replace(" Stone", "");
          if (s.gems == null) return `${label} s/ preço`;
          const avg = s.avg != null && s.avg > s.gems ? ` (média ${num(s.avg)})` : "";
          const queue = s.queue != null ? `, fila ${num(s.queue)}` : "";
          return `${label} ${num(s.gems)}${avg} · ${num(s.soldWeek)}/sem${queue}`;
        })
        .join(", ");

/** Hunts visitadas no período (o que renderam) e o catálogo alcançável (o que a pedra vale). */
export async function loadHunts(
  supabase: SupabaseClient,
  { conta, period, q, nicks, farm }: { conta: string | null; period: Period; q: string; nicks: Map<string, string>; farm: string[] },
) {
  const since = new Date(Date.now() - Number(period) * 86400_000).toISOString();
  const ids = conta ? [conta] : farm;
  const [sumRes, huntsRes, species, loot, priceInfo, levelRes, currentRes, perAccRes, profRes] = await Promise.all([
    supabase.rpc("hunt_summary", { p_since: since, p_account: conta }),
    supabase.from("game_hunts").select("slug, name, level, area, region, species_id, species_name").order("level").limit(2000),
    loadAllSpecies(supabase),
    loadLootStones(supabase),
    loadStonePrices(supabase),
    supabase.from("events").select("data->trainer_level").in("type", ["gems.plan", "outland.potential", "rank.plan"])
      .order("received_at", { ascending: false }).limit(1).maybeSingle(),
    supabase.from("events").select("account_id, received_at, data->slug").eq("type", "hunt.changed")
      .order("received_at", { ascending: false }).limit(50),
    Promise.all(ids.map((id) => supabase.rpc("hunt_summary", { p_since: since, p_account: id }))),
    supabase.from("account_profile").select("account_id, level, hunt_slug").in("account_id", ids),
  ]);

  const catalog = new Map(((huntsRes.data ?? []) as CatalogHunt[]).map((h) => [h.slug, h]));
  const parents = parentsOf(species);
  // o catálogo vai até o nível da conta escolhida (em "Todas", da conta de nível mais alto)
  const profs = (profRes.data ?? []) as { account_id: string; level: number | null; hunt_slug: string | null }[];
  const level = Math.max(0, ...profs.map((p) => p.level ?? 0))
    || Number((levelRes.data as { trainer_level?: number } | null)?.trainer_level) || null;
  // hunt atual de cada conta: o hunt.changed mais recente
  const current = new Map<string, { nick: string; at: string }>();
  const seenAcc = new Set<string>();
  for (const r of (currentRes.data ?? []) as { account_id: string; received_at: string; slug: string }[]) {
    if (seenAcc.has(r.account_id) || (conta && r.account_id !== conta)) continue;
    seenAcc.add(r.account_id);
    current.set(r.slug, { nick: nicks.get(r.account_id) ?? "?", at: r.received_at });
  }

  // por conta: a hunt de agora (do perfil, senão do último hunt.changed) e o resumo do período
  const lastChange = new Map<string, { slug: string; at: string }>();
  for (const r of (currentRes.data ?? []) as { account_id: string; received_at: string; slug: string }[]) {
    if (!lastChange.has(r.account_id)) lastChange.set(r.account_id, { slug: r.slug, at: r.received_at });
  }
  const perAccount: AccountHunts[] = ids.map((id, i) => {
    const prof = profs.find((p) => p.account_id === id);
    const rows = ((perAccRes[i]?.data ?? []) as Summary[]).filter((s) => s.active_minutes > 0 || s.kills > 0)
      .sort((a, b) => b.active_minutes - a.active_minutes);
    const sum = (f: (s: Summary) => number) => rows.reduce((t, s) => t + (Number(f(s)) || 0), 0);
    const lc = lastChange.get(id) ?? null;
    return {
      id, nick: nicks.get(id) ?? "?", level: prof?.level ?? null,
      current: prof?.hunt_slug ? { slug: prof.hunt_slug, at: lc?.slug === prof.hunt_slug ? lc.at : "" } : lc,
      visited: rows,
      totals: {
        minutes: sum((s) => s.active_minutes), kills: sum((s) => s.kills), gems: sum((s) => s.drops_value_orb),
        goldNet: sum((s) => s.gold_net), captures: sum((s) => s.captures), shinies: sum((s) => s.shinies),
      },
    };
  });

  const stonesFor = (h: CatalogHunt) =>
    stonesOf(species.get(h.species_id), loot.byType, loot.chances[chainPosition(species, parents, h.species_id)], priceInfo.prices);

  const visited = ((sumRes.data ?? []) as Summary[])
    .filter((s) => s.active_minutes > 0 || s.kills > 0)
    .sort((a, b) => (perHour(b.drops_value_orb, b.active_minutes) ?? 0) - (perHour(a.drops_value_orb, a.active_minutes) ?? 0) || b.active_minutes - a.active_minutes);
  const kphOf = new Map(visited.filter((v) => v.active_minutes >= 5).map((v) => [v.hunt_slug, (v.kills * 60) / v.active_minutes]));

  const reachable: Reachable[] = [...catalog.values()]
    .filter((h) => (level == null || h.level <= level) && (!q || `${h.slug} ${h.species_name ?? ""} ${h.name ?? ""}`.toLowerCase().includes(q)))
    .map((h) => {
      const stones = stonesFor(h);
      const g1000 = gemsPer1000(stones);
      const kph = kphOf.get(h.slug) ?? null;
      return { h, stones, g1000, kph, gemsHour: kph != null ? (kph * g1000) / 1000 : null };
    })
    .sort((a, b) => b.g1000 - a.g1000 || a.h.level - b.h.level)
    .slice(0, q ? 200 : 60);

  const accSlugs = perAccount.flatMap((a) => [...a.visited.map((v) => v.hunt_slug), ...(a.current ? [a.current.slug] : [])]);
  const huntSpecies = [...new Set([...visited.map((v) => catalog.get(v.hunt_slug)?.species_id), ...reachable.map((r) => r.h.species_id),
    ...accSlugs.map((s) => catalog.get(s)?.species_id)]
    .filter((x): x is number => x != null))];
  const looktypes = await speciesLooktypes(supabase, huntSpecies);

  // dados da gaveta de cada hunt (clicar no nome abre; HuntDrawer.tsx)
  const details: Record<string, HuntDetail> = {};
  const detailOf = (h: CatalogHunt): HuntDetail => {
    const v = visited.find((x) => x.hunt_slug === h.slug);
    const stones = stonesFor(h);
    const measured = v ? [
      { label: "Tempo no período", value: v.active_minutes >= 60 ? `${num(v.active_minutes / 60)} h` : `${num(v.active_minutes)} min` },
      { label: "Abates por hora", value: num(perHour(v.kills, v.active_minutes)) },
      { label: "Gemas por hora", value: num(perHour(v.drops_value_orb, v.active_minutes)) },
      { label: "Ouro líquido por hora", value: num(perHour(v.gold_net, v.active_minutes), { compact: true }) },
      { label: "Capturas", value: `${num(v.captures)}${v.shinies ? ` (${num(v.shinies)} shiny)` : ""}` },
    ] : [];
    return {
      slug: h.slug, title: h.species_name ?? h.name ?? h.slug, speciesId: h.species_id, level: h.level,
      area: [...new Set([h.region, h.area].filter(Boolean))].join(" · "), stones: stoneText(stones),
      gemsPer1000: gemsPer1000(stones), measured,
      here: [...current.entries()].filter(([slug]) => slug === h.slug).map(([, c]) => c.nick),
    };
  };
  for (const v of visited) { const h = catalog.get(v.hunt_slug); if (h) details[h.slug] = detailOf(h); }
  for (const slug of accSlugs) { const h = catalog.get(slug); if (h) details[h.slug] ??= detailOf(h); }
  for (const r of reachable) details[r.h.slug] ??= detailOf(r.h);

  // só as hunts que a página mostra (o catálogo inteiro tem 1.043 e iria todo para o cache)
  const shown = new Map<string, CatalogHunt>();
  for (const v of visited) { const h = catalog.get(v.hunt_slug); if (h) shown.set(h.slug, h); }
  for (const slug of accSlugs) { const h = catalog.get(slug); if (h) shown.set(h.slug, h); }

  return {
    perAccount,
    visited, catalog: shown, current, reachable, details, level, looktypes,
    pricesAt: priceInfo.takenAt,
    err: sumRes.error?.message ?? huntsRes.error?.message ?? perAccRes.find((r) => r.error)?.error?.message ?? null,
  };
}
