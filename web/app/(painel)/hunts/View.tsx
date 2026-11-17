"use client";

import Form from "next/form";
import { useSearchParams } from "next/navigation";
import { Ld, LdRows } from "@/components/Loading";
import { AccountTabs, Bar, ErrorNote, LinkTabs, PageHeader, Panel } from "@/components/Page";
import { Sprite } from "@/components/Sprite";
import { ago, num } from "@/lib/format";
import type { CatalogHunt } from "@/lib/hunts";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import { loadHunts, perHour, PERIODS, stoneText, type Period } from "./data";
import { HuntDrawerProvider, HuntOpen } from "./HuntDrawer";

/** Painel de hunts: as visitadas (o que renderam) e o catálogo alcançável (o que a pedra vale). */
export function HuntsView() {
  const sp = useSearchParams();
  const dias = sp.get("dias");
  const period: Period = dias === "1" || dias === "30" ? dias : "7";
  const q = (sp.get("q") ?? "").trim().toLowerCase();
  const accountsQ = useAccounts();
  const accounts = accountsQ.data ?? [];
  const conta = accounts.find((a) => a.id === sp.get("conta"))?.id ?? null;
  const nicks = new Map(accounts.map((a) => [a.id, a.nick]));
  const { data: d } = usePanel(["hunts", conta, period, q], (sb) => loadHunts(sb, { conta, period, q, nicks }),
    { enabled: accountsQ.isSuccess });
  const { data: atlas = null } = useAtlas();

  const maxGems = Math.max(0, ...(d?.visited ?? []).map((v) => perHour(v.drops_value_orb, v.active_minutes) ?? 0));
  const maxG1000 = Math.max(0, ...(d?.reachable ?? []).map((r) => r.g1000));
  const face = (h: CatalogHunt | undefined) =>
    h ? <Sprite mon={{ id: h.species_id, species_id: h.species_id, name: h.species_name ?? undefined }} atlas={atlas} looktypes={d?.looktypes} size={32} /> : null;
  const open = (h: CatalogHunt | undefined, label: React.ReactNode, fallback: string) =>
    h ? <HuntOpen slug={h.slug}>{face(h)}{label}</HuntOpen> : <>{label ?? fallback}</>;

  const link = (over: Record<string, string | null>) => {
    const p = new URLSearchParams();
    const c = "conta" in over ? over.conta : conta;
    const ds = "dias" in over ? over.dias : period;
    if (c) p.set("conta", c);
    if (ds && ds !== "7") p.set("dias", ds);
    if (q) p.set("q", q);
    const s = p.toString();
    return s ? `/hunts?${s}` : "/hunts";
  };

  const body = (
    <div className="stack">
      <Panel title="Visitadas" meta={PERIODS[period]} flush
        hint="Gemas/h: os drops reais pela média do Mercado na hora de cada drop. Poucos minutos numa hunt dão números instáveis.">
        {d && d.visited.length === 0 ? (
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
              {!d && <LdRows cols={11} rows={5} />}
              {d?.visited.map((v) => {
                const h = d.catalog.get(v.hunt_slug);
                const cur = d.current.get(v.hunt_slug);
                return (
                  <tr key={v.hunt_slug}>
                    <td className="hunt-cell">
                      {open(h, h?.species_name ?? h?.name ?? v.hunt_slug, v.hunt_slug)}
                      {cur && <span className="badge ready" style={{ marginLeft: ".4rem" }}>agora · {cur.nick}</span>}
                    </td>
                    <td>{h?.level ?? "—"}</td>
                    <td>{v.active_minutes >= 60 ? `${num(v.active_minutes / 60)} h` : `${num(v.active_minutes)} min`}</td>
                    <td>{num(perHour(v.kills, v.active_minutes))}</td>
                    <td><Bar value={perHour(v.drops_value_orb, v.active_minutes)} max={maxGems} tone="gem"
                      label={<strong>{num(perHour(v.drops_value_orb, v.active_minutes))}</strong>} /></td>
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
      </Panel>

      <Panel title={<>Catálogo{d?.level ? ` até o nível ${d.level}` : ""}</>} flush hint={<>
          <p>Gemas / 1.000 abates = Σ chance da pedra × preço de venda: o menor entre a média de 7 dias e o menor anúncio
            aberto{d?.pricesAt ? ` (preços de ${ago(d.pricesAt)})` : ""}.</p>
          <p>Pedra que vende pouco por semana não aguenta volume: o foco gemas só conta até 10% do vendido.</p>
        </>} meta={
          <Form action="/hunts" className="row" scroll={false}>
            {conta && <input type="hidden" name="conta" value={conta} />}
            {period !== "7" && <input type="hidden" name="dias" value={period} />}
            <input name="q" defaultValue={q} placeholder="buscar hunt ou espécie" />
            <button type="submit" className="ghost small">Buscar</button>
          </Form>
        }>
        <table>
          <thead>
            <tr><th>Hunt</th><th>Nível</th><th>Área</th><th>Pedras (preço de venda, vendidas/semana, fila)</th><th>Gemas / 1.000 abates</th><th>Abates/h medidos</th><th>Gemas/h</th></tr>
          </thead>
          <tbody>
            {!d && <LdRows cols={7} rows={8} />}
            {d?.reachable.map(({ h, stones, g1000, kph, gemsHour }) => (
              <tr key={h.slug}>
                <td className="hunt-cell">
                  {open(h, h.species_name ?? h.name ?? h.slug, h.slug)}
                  {d.current.has(h.slug) && <span className="badge ready" style={{ marginLeft: ".4rem" }}>agora</span>}
                </td>
                <td>{h.level}</td>
                <td className="small">{[...new Set([h.region, h.area].filter(Boolean))].join(" · ")}</td>
                <td className="small">{stoneText(stones)}</td>
                <td><Bar value={g1000} max={maxG1000} tone="gem" label={<strong>{num(g1000)}</strong>} /></td>
                <td>{kph == null ? <span className="muted">—</span> : num(kph)}</td>
                <td>{gemsHour == null ? <span className="muted">—</span> : num(gemsHour)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );

  return (
    <>
      <PageHeader title="Hunts">
        <AccountTabs accounts={accounts} chosen={conta} href={(id) => link({ conta: id })} />
        <LinkTabs label="Período" items={(Object.keys(PERIODS) as Period[]).map((p) => ({ key: p, href: link({ dias: p }), label: PERIODS[p], active: p === period }))} />
      </PageHeader>
      <ErrorNote message={d?.err ?? accountsQ.error?.message} />
      {d ? (
        <HuntDrawerProvider key={conta ?? "todas"} hunts={d.details}
          accounts={accounts.filter((a) => a.role === "farm").map((a) => ({ id: a.id, nick: a.nick, enabled: a.enabled }))}
          defaultAccount={conta} atlas={atlas} looktypes={Object.fromEntries(d.looktypes)}>
          {body}
        </HuntDrawerProvider>
      ) : body}
    </>
  );
}
