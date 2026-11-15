import Link from "next/link";
import { Shell } from "@/components/Shell";
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
        .map((s) => `${s.name.replace(" Stone", "")} ${s.gems == null ? "s/ preço" : `${num(s.gems)} (${num(s.soldWeek)}/sem)`}`)
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
      <h1>Hunts</h1>
      <p className="small">
        {[null, ...accounts].map((a) => (
          <span key={a?.id ?? "todas"} style={{ marginRight: ".75rem" }}>
            {(a?.id ?? null) === (chosen?.id ?? null) ? <strong>{a?.nick ?? "Todas"}</strong> : <Link href={link({ conta: a?.id ?? null })}>{a?.nick ?? "Todas"}</Link>}
          </span>
        ))}
        <span className="muted"> · </span>
        {(Object.keys(PERIODS) as Period[]).map((p) => (
          <span key={p} style={{ marginRight: ".75rem" }}>
            {p === period ? <strong>{PERIODS[p]}</strong> : <Link href={link({ dias: p })}>{PERIODS[p]}</Link>}
          </span>
        ))}
      </p>
      {err && <p className="error">Erro ao ler o Supabase: {err}</p>}

      <section className="card" style={{ overflowX: "auto" }}>
        <h2 style={{ marginTop: 0 }}>Visitadas ({PERIODS[period]})</h2>
        {visited.length === 0 ? (
          <p className="muted">Nenhuma hunt com abates no período.</p>
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
                    <td>
                      {h?.species_name ?? h?.name ?? v.hunt_slug}
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
        <p className="muted small" style={{ marginBottom: 0 }}>
          Gemas/h: o valor dos drops reais pela média do Mercado na hora de cada drop. Poucos minutos numa hunt dão números instáveis.
        </p>
      </section>

      <section className="card" style={{ overflowX: "auto", marginTop: "1rem" }}>
        <div className="spread">
          <h2 style={{ margin: 0 }}>Catálogo {level ? `até o nível ${level}` : ""}</h2>
          <form action="/hunts" className="row">
            {chosen && <input type="hidden" name="conta" value={chosen.id} />}
            {period !== "7" && <input type="hidden" name="dias" value={period} />}
            <input name="q" defaultValue={q} placeholder="buscar hunt ou espécie" />
            <button type="submit">Buscar</button>
          </form>
        </div>
        <table style={{ marginTop: ".75rem" }}>
          <thead>
            <tr><th>Hunt</th><th>Nível</th><th>Área</th><th>Pedras (gemas e vendidas por semana)</th><th>Gemas / 1.000 abates</th><th>Abates/h medidos</th><th>Gemas/h</th></tr>
          </thead>
          <tbody>
            {reachable.map(({ h, stones, g1000, kph, gemsHour }) => (
              <tr key={h.slug}>
                <td>
                  {h.species_name ?? h.name ?? h.slug}
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
        <p className="muted small" style={{ marginBottom: 0 }}>
          Gemas / 1.000 abates = Σ chance da pedra × preço médio em gemas (último snapshot{priceInfo.takenAt ? ` de ${ago(priceInfo.takenAt)}` : ""}).
          Não depende do ritmo: multiplique pelos abates/h da hunt. Pedra que vende pouco por semana (ex.: Thunder) não
          aguenta muito volume: o foco gemas só conta até 10% do vendido por semana, com o ritmo medido.
        </p>
      </section>
    </Shell>
  );
}
