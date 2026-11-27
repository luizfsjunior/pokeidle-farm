"use client";

import Link from "next/link";
import { Alerts } from "@/components/Alerts";
import { CommandStatus } from "@/components/CommandStatus";
import { Icon } from "@/components/icons";
import { Ld, LdBlock } from "@/components/Loading";
import { ErrorNote, Kpi, PageHeader, Stat } from "@/components/Page";
import { TrainerCard } from "@/components/TrainerCard";
import { ago, num, pct, todaySP } from "@/lib/format";
import { farmTime, hoursToLevel, supplies } from "@/lib/supplies";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import type { Account } from "@/lib/types";
import { useCommand } from "@/lib/useCommand";
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
  const farmTotals = d ? farm.map((a) => d.totals.get(a.id)).filter((t): t is Totals => !!t) : [];
  const sumFarm = (k: keyof Totals) => farmTotals.reduce((s, t) => s + t[k], 0);
  const sumToday = (k: keyof Totals) => (d ? [...d.totals.values()].reduce((s, t) => s + t[k], 0) : 0);
  const v = (x: React.ReactNode, w?: string) => (d ? x : <Ld w={w} />);

  return (
    <>
      <PageHeader
        title="Contas"
        subtitle={`Hoje, ${today.split("-").reverse().join("/")}`}
        hint={<><p>Números do dia por hora ativa, recalculados a cada 10 min. Gemas: drops pelo preço do Mercado, sem as
          pedras (não são fonte de gemas).</p><p>Moedas, equipe, HP, poções, revives e bolas vêm do perfil, a cada 2 min. O tempo até o próximo nível é o
          XP que falta dividido pelo XP por hora ativa de hoje.</p><p>O histórico de 7, 30 e 90 dias fica em Histórico.</p></>}
      />
      <ErrorNote message={d?.err} />
      {d && accounts.length === 0 && !d.err && (
        <div className="card">Nenhuma conta cadastrada para este usuário. Veja <code>docs/deploy.md</code>.</div>
      )}
      {(!d || accounts.length > 0) && (
        <div className="kpis" style={{ marginBottom: "1.25rem" }}>
          <Kpi label="Contas conectadas" value={v(`${online} de ${farm.length}`, "5ch")} tone={d && online === farm.length && farm.length > 0 ? "good" : undefined} />
          <Kpi label="Ouro nas contas" value={v(num(sumProfile("gold"), { compact: true }))} tone="gold" />
          <Kpi label="Gemas de hoje (farm)" value={v(num(sumFarm("drops_value_orb")))} tone="gem" note={d ? `${num(sumToday("kills"))} abates` : <Ld w="8ch" />} />
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
          const profile = d.profiles.get(a.id);
          const sup = supplies(profile);
          const toLevel = hoursToLevel(profile, perHour(t?.xp ?? 0, mins));
          return (
            <TrainerCard key={a.id} account={a} profile={profile} atlas={atlas} looktypes={d.looktypes}
              href={`/contas/${a.id}`} compact>
              <Alerts items={d.alerts.get(a.id)} compact />
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
                {sup && (
                  <div className="stats stats-4 supplies">
                    <Stat label="HP do ativo" value={<span className={sup.hpPct != null && sup.hpPct < 0.3 ? "warn-text" : undefined}>{pct(sup.hpPct, 0)}</span>} />
                    <Stat label="Poções" value={num(sup.potions)} />
                    <Stat label="Revives" value={num(sup.revives)} />
                    <Stat label="Bolas" value={num(sup.balls, { compact: true })} />
                  </div>
                )}
                {toLevel != null && (
                  <div className="small secondary" title="XP que falta para o próximo nível ÷ XP por hora ativa de hoje">
                    Próximo nível em ~{farmTime(toLevel)} de farm
                  </div>
                )}
                {rank && (
                  <div className="small">
                    Rank: {num(rank.species ?? 0)} espécies na semana{rank.target && <>, alvo {rank.target}</>}
                  </div>
                )}
              </div>
              <CardActions account={a} />
            </TrainerCard>
          );
        })}
      </div>
    </>
  );
}

/** No cartão da visão geral: só Abrir, e Reconectar quando a conta ligada não está pronta. Os outros comandos ficam na conta. */
function CardActions({ account }: { account: Account }) {
  const { send, cmd, error, busy } = useCommand();
  const stuck = account.enabled && account.status !== "ready";
  return (
    <div className="card-actions">
      {stuck && (
        <button className="ghost small" disabled={busy} onClick={() => void send(account.id, "session.reconnect")}>Reconectar</button>
      )}
      <CommandStatus cmd={cmd} error={error} inline />
      <Link href={`/contas/${account.id}`} className="btn-link" style={{ marginLeft: "auto" }}>Abrir <Icon name="arrow" size={16} /></Link>
    </div>
  );
}
