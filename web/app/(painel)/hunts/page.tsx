import Link from "next/link";
import { AccountTabs, ErrorNote, LinkTabs, PageHeader, Panel } from "@/components/Page";
import { Shell } from "@/components/Shell";
import { HuntDrawerProvider, HuntOpen, type HuntDetail } from "./HuntDrawer";
import { Sprite } from "@/components/Sprite";
import { loadAtlas, speciesLooktypes } from "@/lib/sprites";
import { ago, num } from "@/lib/format";
import {
  chainPosition,
  gemsPer1000,
  loadAllSpecies,
  loadLootStones,
  loadStonePrices,
  parentsOf,
  stonesOf,
  type CatalogHunt,
  type Stone,
} from "@/lib/hunts";
import { requireUser } from "@/lib/supabase/server";
import type { Account } from "@/lib/types";

export const dynamic = "force-dynamic";

const PERIODS = { "1": "24 h", "7": "7 dias", "30": "30 dias" } as const;
type Period = keyof typeof PERIODS;

type Summary = {
  hunt_slug: string;
  kills: number;
  active_minutes: number;
  gold: number;
  gold_net: number;
  drops: number;
  drops_value_orb: number;
  drops_value_gold: number;
  capture_attempts: number;
  captures: number;
  shinies: number;
  rank_points: number;
  last_hour: string;
};

const perHour = (v: number, mins: number) => (mins > 0 ? (v * 60) / mins : null);
const stoneText = (stones: Stone[]) =>
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

/** Painel de hunts: as visitadas (o que renderam) e o catálogo alcançável (o que a pedra vale). */
export default async function HuntsPage({ searchParams }: { searchParams: Promise<{ conta?: string; dias?: string; q?: string }> }) {
  const sp = await searchParams;
  const period: Period = sp.dias === "1" || sp.dias === "30" ? sp.dias : "7";
  const q = (sp.q ?? "").trim().toLowerCase();
  const { supabase, email } = await requireUser();

  const accountsRes = await supabase.from("accounts").select("id, nick, role, enabled, status").order("nick");
  const accounts = (accountsRes.data ?? []) as Account[];
  const chosen = accounts.find((a) => a.id === sp.conta) ?? null;
  const since = new Date(Date.now() - Number(period) * 86400_000).toISOString();

  const [sumRes, huntsRes, species, loot, priceInfo, levelRes, currentRes] = await Promise.all([
    supabase.rpc("hunt_summary", { p_since: since, p_account: chosen?.id ?? null }),
    supabase.from("game_hunts").select("slug, name, level, area, region, species_id, species_name").order("level").limit(2000),
    loadAllSpecies(supabase),
    loadLootStones(supabase),
    loadStonePrices(supabase),
    supabase.from("events").select("data->trainer_level").in("type", ["gems.plan", "gems.potential", "rank.plan"])
      .order("received_at", { ascending: false }).limit(1).maybeSingle(),
    supabase.from("events").select("account_id, received_at, data->slug").eq("type", "hunt.changed")
      .order("received_at", { ascending: false }).limit(50),
  ]);

  const catalog = new Map(((huntsRes.data ?? []) as CatalogHunt[]).map((h) => [h.slug, h]));
  const parents = parentsOf(species);
  const level = Number((levelRes.data as { trainer_level?: number } | null)?.trainer_level) || null;
  // hunt atual de cada conta: o hunt.changed mais recente
  const current = new Map<string, { nick: string; at: string }>();
  const seenAcc = new Set<string>();
  for (const r of (currentRes.data ?? []) as { account_id: string; received_at: string; slug: string }[]) {
    if (seenAcc.has(r.account_id) || (chosen && r.account_id !== chosen.id)) continue;
    seenAcc.add(r.account_id);
    current.set(r.slug, { nick: accounts.find((a) => a.id === r.account_id)?.nick ?? "?", at: r.received_at });
  }

  const stonesFor = (h: CatalogHunt) =>
    stonesOf(species.get(h.species_id), loot.byType, loot.chances[chainPosition(species, parents, h.species_id)], priceInfo.prices);

  const visited = ((sumRes.data ?? []) as Summary[])
    .filter((s) => s.active_minutes > 0 || s.kills > 0)
    .sort((a, b) => (perHour(b.drops_value_orb, b.active_minutes) ?? 0) - (perHour(a.drops_value_orb, a.active_minutes) ?? 0) || b.active_minutes - a.active_minutes);
  const kphOf = new Map(visited.filter((v) => v.active_minutes >= 5).map((v) => [v.hunt_slug, (v.kills * 60) / v.active_minutes]));

  const reachable = [...catalog.values()]
    .filter((h) => (level == null || h.level <= level) && (!q || `${h.slug} ${h.species_name ?? ""} ${h.name ?? ""}`.toLowerCase().includes(q)))
    .map((h) => {
      const stones = stonesFor(h);
      const g1000 = gemsPer1000(stones);
      const kph = kphOf.get(h.slug) ?? null;
      return { h, stones, g1000, kph, gemsHour: kph != null ? (kph * g1000) / 1000 : null };
    })
    .sort((a, b) => b.g1000 - a.g1000 || a.h.level - b.h.level)
    .slice(0, q ? 200 : 60);

  // retrato da espécie de cada hunt (atlas do jogo por looktype)
  const huntSpecies = [...new Set([...visited.map((v) => catalog.get(v.hunt_slug)?.species_id), ...reachable.map((r) => r.h.species_id)]
    .filter((x): x is number => x != null))];
  const [atlas, looktypes] = await Promise.all([loadAtlas(), speciesLooktypes(supabase, huntSpecies)]);
  const face = (h: CatalogHunt | undefined) =>
    h ? <Sprite mon={{ id: h.species_id, species_id: h.species_id, name: h.species_name ?? undefined }} atlas={atlas} looktypes={looktypes} size={32} /> : null;

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
  for (const r of reachable) details[r.h.slug] ??= detailOf(r.h);
  const open = (h: CatalogHunt | undefined, label: React.ReactNode, fallback: string) =>
    h ? <HuntOpen slug={h.slug}>{face(h)}{label}</HuntOpen> : <>{label ?? fallback}</>;

  const link = (over: Record<string, string | null>) => {
    const p = new URLSearchParams();
    const conta = "conta" in over ? over.conta : chosen?.id ?? null;
    const dias = "dias" in over ? over.dias : period;
    if (conta) p.set("conta", conta);
    if (dias && dias !== "7") p.set("dias", dias);
    if (q) p.set("q", q);
    const s = p.toString();
    return s ? `/hunts?${s}` : "/hunts";
  };
  const err = accountsRes.error?.message ?? sumRes.error?.message ?? huntsRes.error?.message;

  return (
    <Shell email={email}>
      <PageHeader title="Hunts" subtitle="Onde cada conta rendeu e o que cada hunt promete em gemas.">
        <AccountTabs accounts={accounts} chosen={chosen?.id ?? null} href={(id) => link({ conta: id })} />
        <LinkTabs label="Período" items={(Object.keys(PERIODS) as Period[]).map((p) => ({ key: p, href: link({ dias: p }), label: PERIODS[p], active: p === period }))} />
      </PageHeader>
      <ErrorNote message={err} />
      <HuntDrawerProvider hunts={details} accounts={accounts.filter((a) => a.role === "farm").map((a) => ({ id: a.id, nick: a.nick, enabled: a.enabled }))}
        defaultAccount={chosen?.id ?? null} atlas={atlas} looktypes={Object.fromEntries(looktypes)}>
      <div className="stack">

      <Panel title="Visitadas" meta={PERIODS[period]} flush>
        {visited.length === 0 ? (
          <p className="panel-empty">Nenhuma hunt com abates no período.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Hunt</th><th>Nível</th><th>Tempo</th><th>Abates/h</th><th>Gemas/h</th><th>Ouro/h</th>
                <th>Ouro líquido/h</th><th>Drops</th><th>Capturas</th><th>Espécies novas</th><th>Última vez</th>
              </tr>
            </thead>
            <tbody>
              {visited.map((v) => {
                const h = catalog.get(v.hunt_slug);
                const cur = current.get(v.hunt_slug);
                return (
                  <tr key={v.hunt_slug}>
                    <td className="hunt-cell">
                      {open(h, h?.species_name ?? h?.name ?? v.hunt_slug, v.hunt_slug)}
                      {cur && <span className="badge ready" style={{ marginLeft: ".4rem" }}>agora · {cur.nick}</span>}
                    </td>
                    <td>{h?.level ?? "—"}</td>
                    <td>{v.active_minutes >= 60 ? `${num(v.active_minutes / 60)} h` : `${num(v.active_minutes)} min`}</td>
                    <td>{num(perHour(v.kills, v.active_minutes))}</td>
                    <td><strong>{num(perHour(v.drops_value_orb, v.active_minutes))}</strong></td>
                    <td>{num(perHour(v.gold, v.active_minutes), { compact: true })}</td>
                    <td>{num(perHour(v.gold_net, v.active_minutes), { compact: true })}</td>
                    <td>{num(v.drops)}</td>
                    <td>{num(v.captures)}{v.shinies > 0 && <span className="small"> ({num(v.shinies)} shiny)</span>}</td>
                    <td>{num(v.rank_points)}</td>
                    <td className="muted small">{ago(v.last_hour)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <p className="panel-note">
          Gemas/h: o valor dos drops reais pela média do Mercado na hora de cada drop. Poucos minutos numa hunt dão números instáveis.
        </p>
      </Panel>

      <Panel title={`Catálogo${level ? ` até o nível ${level}` : ""}`} flush meta={
          <form action="/hunts" className="row">
            {chosen && <input type="hidden" name="conta" value={chosen.id} />}
            {period !== "7" && <input type="hidden" name="dias" value={period} />}
            <input name="q" defaultValue={q} placeholder="buscar hunt ou espécie" />
            <button type="submit" className="ghost small">Buscar</button>
          </form>
        }>
        <table>
          <thead>
            <tr><th>Hunt</th><th>Nível</th><th>Área</th><th>Pedras (preço de venda, vendidas/semana, fila)</th><th>Gemas / 1.000 abates</th><th>Abates/h medidos</th><th>Gemas/h</th></tr>
          </thead>
          <tbody>
            {reachable.map(({ h, stones, g1000, kph, gemsHour }) => (
              <tr key={h.slug}>
                <td className="hunt-cell">
                  {open(h, h.species_name ?? h.name ?? h.slug, h.slug)}
                  {current.has(h.slug) && <span className="badge ready" style={{ marginLeft: ".4rem" }}>agora</span>}
                </td>
                <td>{h.level}</td>
                <td className="small">{[...new Set([h.region, h.area].filter(Boolean))].join(" · ")}</td>
                <td className="small">{stoneText(stones)}</td>
                <td><strong>{num(g1000)}</strong></td>
                <td>{kph == null ? <span className="muted">—</span> : num(kph)}</td>
                <td>{gemsHour == null ? <span className="muted">—</span> : num(gemsHour)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="panel-note">
          Gemas / 1.000 abates = Σ chance da pedra × preço de venda em gemas: o menor entre a média de 7 dias e o menor
          anúncio aberto, que é o preço de hoje (último snapshot{priceInfo.takenAt ? ` de ${ago(priceInfo.takenAt)}` : ""}).
          Não depende do ritmo: multiplique pelos abates/h da hunt. Pedra que vende pouco por semana (ex.: Thunder) não
          aguenta muito volume: o foco gemas só conta até 10% do vendido por semana, com o ritmo medido.
        </p>
      </Panel>
      </div>
      </HuntDrawerProvider>
    </Shell>
  );
}
