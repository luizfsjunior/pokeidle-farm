import type { SupabaseClient } from "@supabase/supabase-js";
import { loadAllHunts } from "@/lib/catalog";
import { num } from "@/lib/format";
import { speciesLooktypes } from "@/lib/sprites";
import type { HuntDetail } from "./HuntDrawer";

export const PERIODS = { "1": "24 h", "7": "7 dias", "30": "30 dias", "90": "90 dias" } as const;
export type Period = keyof typeof PERIODS;

export type CatalogHunt = { slug: string; name: string | null; level: number; area: string | null; region: string | null; species_id: number; species_name: string | null };
export type Summary = {
  hunt_slug: string; kills: number; xp: number; active_minutes: number; gold: number; gold_net: number; drops: number;
  drops_value_orb: number; drops_value_gold: number; capture_attempts: number; captures: number; shinies: number;
  rank_points: number; last_hour: string;
};

/** Uma conta na sanfona: onde está agora e o que cada hunt rendeu para ela no período. */
export type AccountHunts = {
  id: string; nick: string; level: number | null; current: string | null; visited: Summary[];
  totals: { minutes: number; kills: number; xp: number; gems: number; goldNet: number; captures: number; shinies: number };
};

export const perHour = (v: number, mins: number) => (mins > 0 ? (v * 60) / mins : null);
export const dur = (m: number) => (m >= 60 ? `${num(m / 60)} h` : `${num(m)} min`);
const sumOf = (rows: Summary[], f: (s: Summary) => number) => rows.reduce((t, s) => t + (Number(f(s)) || 0), 0);

/**
 * O que cada conta rendeu em cada hunt no período (função `hunt_summary`) e onde ela está agora. O catálogo
 * por pedra saiu (docs/design/painel-ux-v2.md): pedra não é fonte de gemas.
 */
export async function loadHunts(
  supabase: SupabaseClient,
  { period, ids, nicks }: { period: Period; ids: string[]; nicks: Map<string, string> },
) {
  const since = new Date(Date.now() - Number(period) * 86400_000).toISOString();
  const [huntsRes, perAccRes, profRes] = await Promise.all([
    loadAllHunts<CatalogHunt>(supabase, "slug, name, level, area, region, species_id, species_name"),
    Promise.all(ids.map((id) => supabase.rpc("hunt_summary", { p_since: since, p_account: id }))),
    supabase.from("account_profile").select("account_id, level, hunt_slug").in("account_id", ids),
  ]);
  const all = new Map(huntsRes.data.map((h) => [h.slug, h]));
  const profs = (profRes.data ?? []) as { account_id: string; level: number | null; hunt_slug: string | null }[];

  const perAccount: AccountHunts[] = ids.map((id, i) => {
    const prof = profs.find((p) => p.account_id === id);
    const rows = ((perAccRes[i]?.data ?? []) as Summary[]).filter((s) => s.active_minutes > 0 || s.kills > 0)
      .sort((a, b) => b.active_minutes - a.active_minutes);
    return {
      id, nick: nicks.get(id) ?? "?", level: prof?.level ?? null, current: prof?.hunt_slug ?? null, visited: rows,
      totals: {
        minutes: sumOf(rows, (s) => s.active_minutes), kills: sumOf(rows, (s) => s.kills), xp: sumOf(rows, (s) => s.xp), gems: sumOf(rows, (s) => s.drops_value_orb),
        goldNet: sumOf(rows, (s) => s.gold_net), captures: sumOf(rows, (s) => s.captures), shinies: sumOf(rows, (s) => s.shinies),
      },
    };
  });

  // só as hunts que a página mostra (o catálogo inteiro tem ~1.000 e iria todo para o cache)
  const catalog = new Map<string, CatalogHunt>();
  for (const a of perAccount) {
    for (const slug of [...a.visited.map((v) => v.hunt_slug), ...(a.current ? [a.current] : [])]) {
      const h = all.get(slug);
      if (h) catalog.set(slug, h);
    }
  }
  const looktypes = await speciesLooktypes(supabase, [...new Set([...catalog.values()].map((h) => h.species_id))]);

  // gaveta de cada hunt (clicar no nome abre; HuntDrawer.tsx): os números do período somados entre as contas
  const details: Record<string, HuntDetail> = {};
  for (const h of catalog.values()) {
    const rows = perAccount.flatMap((a) => a.visited.filter((v) => v.hunt_slug === h.slug));
    const mins = sumOf(rows, (s) => s.active_minutes);
    const caps = sumOf(rows, (s) => s.captures);
    const shinies = sumOf(rows, (s) => s.shinies);
    details[h.slug] = {
      slug: h.slug, title: h.species_name ?? h.name ?? h.slug, speciesId: h.species_id, level: h.level,
      area: [...new Set([h.region, h.area].filter(Boolean))].join(" · "),
      measured: rows.length === 0 ? [] : [
        { label: "Tempo no período", value: dur(mins) },
        { label: "Abates por hora", value: num(perHour(sumOf(rows, (s) => s.kills), mins)) },
        { label: "XP por hora", value: num(perHour(sumOf(rows, (s) => s.xp), mins), { compact: true }) },
        { label: "Gemas por hora", value: num(perHour(sumOf(rows, (s) => s.drops_value_orb), mins)) },
        { label: "Ouro líquido por hora", value: num(perHour(sumOf(rows, (s) => s.gold_net), mins), { compact: true }) },
        { label: "Capturas", value: `${num(caps)}${shinies ? ` (${num(shinies)} shiny)` : ""}` },
      ],
      here: perAccount.filter((a) => a.current === h.slug).map((a) => a.nick),
    };
  }

  return {
    perAccount, catalog, details, looktypes,
    err: huntsRes.error ?? perAccRes.find((r) => r.error)?.error?.message ?? null,
  };
}
