"use client";

import { useSearchParams } from "next/navigation";
import { AccountPicker } from "@/components/AccountPicker";
import { LdRows } from "@/components/Loading";
import { ErrorNote, LinkTabs, PageHeader } from "@/components/Page";
import { Sprite } from "@/components/Sprite";
import { ago, nickBadge, num } from "@/lib/format";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import { dur, loadHunts, perHour, PERIODS, type AccountHunts, type CatalogHunt, type Period } from "./data";
import { HuntDrawerProvider, HuntOpen } from "./HuntDrawer";

/** Hunts: o que cada conta rendeu em cada hunt no período e onde ela está agora; clicar abre a gaveta. */
export function HuntsView() {
  const sp = useSearchParams();
  const dias = sp.get("dias");
  const period: Period = dias === "1" || dias === "30" ? dias : "7";
  const accountsQ = useAccounts();
  const accounts = accountsQ.data ?? [];
  const conta = accounts.find((a) => a.id === sp.get("conta"))?.id ?? null;
  const nicks = new Map(accounts.map((a) => [a.id, a.nick]));
  const farm = accounts.filter((a) => a.role === "farm");
  const ids = conta ? [conta] : farm.map((a) => a.id);
  const { data: d } = usePanel(["hunts", period, ids.join(",")], (sb) => loadHunts(sb, { period, ids, nicks }),
    { enabled: accountsQ.isSuccess, refetchInterval: 60_000 });
  const { data: atlas = null } = useAtlas();

  const face = (h: CatalogHunt | undefined) =>
    h ? <Sprite mon={{ id: h.species_id, species_id: h.species_id, name: h.species_name ?? undefined }} atlas={atlas} looktypes={d?.looktypes} size={32} /> : null;
  const link = (over: { conta?: string | null; dias?: string }) => {
    const p = new URLSearchParams();
    const c = "conta" in over ? over.conta : conta;
    const ds = over.dias ?? period;
    if (c) p.set("conta", c);
    if (ds !== "7") p.set("dias", ds);
    const s = p.toString();
    return s ? `/hunts?${s}` : "/hunts";
  };

  const body = (
    <section className="acc-folds" aria-label="Hunts por conta">
      {!d && <LdRows cols={1} rows={4} />}
      {d?.perAccount.map((a) => (
        <AccountFold key={a.id} a={a} open={!!conta || d.perAccount.length === 1} period={period} face={face} catalog={d.catalog} />
      ))}
    </section>
  );

  return (
    <>
      <PageHeader title="Hunts" hint="Gemas/h: o valor dos drops pelo preço do Mercado, sem as pedras (não são fonte de gemas). Toque numa hunt para trocar ou capturar.">
        <AccountPicker accounts={accounts} chosen={conta} hasParam={sp.has("conta")} href={(id) => link({ conta: id })} />
        <LinkTabs label="Período" items={(Object.keys(PERIODS) as Period[]).map((p) => ({ key: p, href: link({ dias: p }), label: PERIODS[p], active: p === period }))} />
      </PageHeader>
      <ErrorNote message={d?.err ?? accountsQ.error?.message} />
      {d ? (
        <HuntDrawerProvider key={conta ?? "todas"} hunts={d.details}
          accounts={farm.map((a) => ({ id: a.id, nick: a.nick, enabled: a.enabled, level: d.perAccount.find((p) => p.id === a.id)?.level ?? null }))}
          defaultAccount={conta} atlas={atlas} looktypes={Object.fromEntries(d.looktypes)}>
          {body}
        </HuntDrawerProvider>
      ) : body}
    </>
  );
}

/** Uma conta como sanfona: no cabeçalho, onde ela está e o que rendeu; aberta, as hunts do período. */
function AccountFold({ a, open, period, face, catalog }: {
  a: AccountHunts;
  open: boolean;
  period: Period;
  face: (h: CatalogHunt | undefined) => React.ReactNode;
  catalog: Map<string, CatalogHunt>;
}) {
  const cur = a.current ? catalog.get(a.current) : undefined;
  const t = a.totals;
  return (
    <details className="fold acc-fold" open={open}>
      <summary className="fold-head acc-head">
        <span className="acc-nick"><span className="tab-avatar" aria-hidden>{nickBadge(a.nick)}</span>{a.nick}
          {a.level != null && <span className="muted small num"> nv {num(a.level)}</span>}</span>
        {/* clicar na hunt abre a gaveta dela sem abrir/fechar a sanfona */}
        <span className="acc-now" onClick={(e) => { if ((e.target as HTMLElement).closest("button, a")) e.preventDefault(); }}>
          {cur ? <HuntOpen slug={cur.slug}>{face(cur)}<span>{cur.species_name ?? cur.name ?? cur.slug}</span>
            <span className="muted small num"> nv {num(cur.level)}</span></HuntOpen>
            : <span className="muted small">{a.current ?? "sem hunt"}</span>}
        </span>
        <span className="acc-stats small num">
          <span title="Tempo caçando no período">{dur(t.minutes)}</span>
          <span title="Gemas por hora no período (sem pedras)"><b>{num(perHour(t.gems, t.minutes))}</b> gemas/h</span>
          <span title="Ouro líquido por hora">{num(perHour(t.goldNet, t.minutes), { compact: true })} ouro/h</span>
          {t.captures > 0 && <span>{num(t.captures)} capturas{t.shinies ? ` · ${num(t.shinies)} ✨` : ""}</span>}
        </span>
        <span className="fold-chevron" aria-hidden />
      </summary>
      {a.visited.length === 0 ? (
        <p className="panel-empty">Nenhuma hunt com abates em {PERIODS[period]}.</p>
      ) : (
        <div className="panel-flush">
          <table>
            <thead>
              <tr><th>Hunt</th><th>Tempo</th><th>Abates/h</th><th>Gemas/h</th><th>Ouro líquido/h</th><th>Capturas</th><th>Última vez</th></tr>
            </thead>
            <tbody>
              {a.visited.map((v) => {
                const h = catalog.get(v.hunt_slug);
                const now = a.current === v.hunt_slug;
                return (
                  <tr key={v.hunt_slug} className={now ? "is-now" : undefined}>
                    <td className="hunt-cell">
                      {h ? <HuntOpen slug={h.slug}>{face(h)}{h.species_name ?? h.name ?? h.slug}<span className="muted small num"> nv {num(h.level)}</span></HuntOpen> : v.hunt_slug}
                      {now && <span className="badge ready" style={{ marginLeft: ".4rem" }}>agora</span>}
                    </td>
                    <td>{dur(v.active_minutes)}</td>
                    <td>{num(perHour(v.kills, v.active_minutes))}</td>
                    <td><strong>{num(perHour(v.drops_value_orb, v.active_minutes))}</strong></td>
                    <td>{num(perHour(v.gold_net, v.active_minutes), { compact: true })}</td>
                    <td>{num(v.captures)}{v.shinies > 0 && <span className="small"> ({num(v.shinies)} ✨)</span>}</td>
                    <td className="muted small">{ago(v.last_hour)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}
