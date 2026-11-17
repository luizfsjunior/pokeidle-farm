"use client";

import { CommandButtons } from "@/components/CommandButtons";
import { Ld, LdBlock } from "@/components/Loading";
import { ErrorNote, Kpi, PageHeader } from "@/components/Page";
import { TrainerCard } from "@/components/TrainerCard";
import { ago, num, todaySP } from "@/lib/format";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import { loadOverview, type Totals } from "./data";

const perHour = (v: number, mins: number) => (mins > 0 ? (v * 60) / mins : null);

export function OverviewView() {
  const today = todaySP();
  const { data: d } = usePanel(["overview", today], loadOverview, { refetchInterval: 60_000 });
  const { data: atlas = null } = useAtlas();
  const known = useAccounts().data;

  const accounts = d?.accounts ?? [];
  const farm = accounts.filter((a) => a.role === "farm");
  const online = farm.filter((a) => a.status === "ready").length;
  const profiles = d ? [...d.profiles.values()] : [];
  const sumProfile = (k: "gold" | "gems" | "diamonds") => profiles.reduce((s, p) => s + (p[k] ?? 0), 0);
  const sumToday = (k: keyof Totals) => (d ? [...d.totals.values()].reduce((s, t) => s + t[k], 0) : 0);
  const v = (x: React.ReactNode, w?: string) => (d ? x : <Ld w={w} />);

  return (
    <>
      <PageHeader
        title="Contas"
        subtitle={`Hoje, ${today.split("-").reverse().join("/")}`}
        hint={<><p>Números do dia por hora ativa, recalculados a cada 10 min.</p><p>Moedas e equipe vêm do perfil, a cada 2 min.</p></>}
      />
      <ErrorNote message={d?.err} />
      {d && accounts.length === 0 && !d.err && (
        <div className="card">Nenhuma conta cadastrada para este usuário. Veja <code>docs/deploy.md</code>.</div>
      )}
      {(!d || accounts.length > 0) && (
        <div className="kpis" style={{ marginBottom: "1.25rem" }}>
          <Kpi label="Contas conectadas" value={v(`${online} de ${farm.length}`, "5ch")} tone={d && online === farm.length && farm.length > 0 ? "good" : undefined} />
          <Kpi label="Ouro nas contas" value={v(num(sumProfile("gold"), { compact: true }))} tone="gold" />
          <Kpi label="Gemas nas contas" value={v(num(sumProfile("gems")))} tone="gem" />
          <Kpi label="Drops de hoje, em gemas" value={v(num(sumToday("drops_value_orb")))} note={d ? `${num(sumToday("kills"))} abates` : <Ld w="8ch" />} />
        </div>
      )}
      <div className="trainers">
        {!d && Array.from({ length: Math.max(1, known?.length ?? 1) }, (_, i) => (
          <section key={i} className="trainer" aria-busy="true"><LdBlock h={360} /></section>
        ))}
        {d?.accounts.map((a) => {
          const t = d.totals.get(a.id);
          const mins = t?.active_minutes ?? 0;
          const rank = d.ranks.get(a.id);
          return (
            <TrainerCard key={a.id} account={a} profile={d.profiles.get(a.id)} atlas={atlas} looktypes={d.looktypes}
              href={`/contas/${a.id}`}>
              <div className="today">
                <div className="today-title small secondary">
                  Por hora hoje{mins ? ` · ${num(mins / 60)} h ativas` : ""} · {ago(d.lastSeen.get(a.id))}
                </div>
                <div className="stats stats-4">
                  <Stat label="XP" value={num(perHour(t?.xp ?? 0, mins), { compact: true })} />
                  <Stat label="Abates" value={num(perHour(t?.kills ?? 0, mins))} />
                  <Stat label="Gemas" value={num(perHour(t?.drops_value_orb ?? 0, mins))} />
                  <Stat label="Ouro líq." value={num(perHour(t?.gold_net ?? 0, mins), { compact: true })} />
                </div>
                {rank && (
                  <div className="small">
                    Rank: {num(rank.species ?? 0)} espécies na semana{rank.target && <>, alvo {rank.target}</>}
                  </div>
                )}
              </div>
              <CommandButtons account={a} />
            </TrainerCard>
          );
        })}
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
