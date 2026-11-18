"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AutoRefresh } from "@/components/AutoRefresh";
import { CommandButtons } from "@/components/CommandButtons";
import { CommandTable } from "@/components/CommandTable";
import { Ld, LdBlock } from "@/components/Loading";
import { Fold, PageHeader, Panel } from "@/components/Page";
import { SectionTabs } from "@/components/SectionTabs";
import { TrainerCard } from "@/components/TrainerCard";
import { TrendChart } from "@/components/TrendChart";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import { loadAccount } from "./data";
import { TeamTrainCard } from "./TeamControls";
import { NewPlugin } from "./NewPlugin";
import { NowCard } from "./NowCard";
import { OutlandCard } from "./OutlandCard";
import { PlanCard } from "./PlanCard";
import { PluginEditor } from "./PluginEditor";
import { ProfileSections } from "./ProfileSections";
import { RankCard } from "./RankCard";

/**
 * Página da conta em 3 abas (docs/design/painel-ux-v2.md, seção 3): Agora (o que ela está fazendo e as ações),
 * Pokémons (equipe, coleção, mochila) e Ajustes (plugins e comandos).
 */
export function AccountView() {
  const { id } = useParams<{ id: string }>();
  const q = usePanel(["account", id], (sb) => loadAccount(sb, id), { refetchInterval: 60_000 });
  const { data: atlas = null } = useAtlas();
  const known = useAccounts().data?.find((a) => a.id === id);
  const d = q.data;
  const account = d?.account ?? known;

  if (q.isSuccess && !d) {
    return <><PageHeader title="Conta" subtitle={<Link href="/">← Contas</Link>} /><p className="muted">Conta não encontrada.</p></>;
  }
  const profile = d?.profile ?? undefined;
  const series = (k: keyof NonNullable<typeof d>["daily"][number]) => (d?.daily ?? []).map((x) => ({ day: x.day, value: x[k] as number | null }));
  const loading = <LdBlock h={220} />;

  return (
    <>
      <PageHeader
        title={account?.nick ?? <Ld w="12ch" />}
        subtitle={<Link href="/">← Contas</Link>}
        actions={account && <CommandButtons account={account} />}
      />
      <SectionTabs tabs={[
        { id: "agora", label: "Agora" },
        { id: "pokemons", label: "Pokémons" },
        { id: "ajustes", label: "Ajustes" },
      ]}>
        {/* Agora */}
        <>
          {!d ? loading : (
            <TrainerCard account={d.account} profile={profile} atlas={atlas} looktypes={d.looktypes} wide hideNick />
          )}
          {d && (
            <NowCard accountId={d.account.id} plugins={d.plugins} capture={d.capture} hold={d.hold} hunts={d.huntOptions}
              huntSlug={profile?.hunt_slug ?? null} trainerLevel={profile?.level ?? null} enabled={d.account.enabled} />
          )}
          {d && <PlanCard plan={d.gemsPlan} progress={d.progress} />}
          {d && <TeamTrainCard accountId={d.account.id} plugins={d.plugins} team={profile?.team ?? []} />}
          {d?.outland && <OutlandCard data={d.outland} progress={d.progress} />}
          {d?.rank && (
            <>
              <AutoRefresh active ms={30_000} queryKey={["account", id]} />
              <RankCard rank={d.rank} />
            </>
          )}
          {d && profile && (
            <Fold title="Bônus e passe">
              <ProfileSections part="status" profile={profile} atlas={atlas} looktypes={d.looktypes} items={d.items} />
            </Fold>
          )}
          {d && profile && (
            <Fold title="Evolução" meta={d.daily.length < 2 ? "a partir do 2º dia" : "por dia, até 90 dias"}>
              <div className="trends">
                <TrendChart title="Nível" points={series("level")} tone="accent" />
                <TrendChart title="XP" points={series("xp")} tone="diamond" compact />
                <TrendChart title="Ouro" points={series("gold")} tone="gold" compact />
                <TrendChart title="Espécies capturadas" points={series("dex_caught")} tone="good" />
                <TrendChart title="Pokémons" points={series("pokemon_count")} tone="accent" />
              </div>
            </Fold>
          )}
        </>

        {/* Pokémons */}
        <>
          {!d ? loading : profile
            ? <ProfileSections part="collection" profile={profile} atlas={atlas} looktypes={d.looktypes} items={d.items} accountId={d.account.id} />
            : <p className="muted">Sem perfil ainda: ele aparece uns segundos depois de o worker conectar a conta.</p>}
        </>

        {/* Ajustes */}
        <>
          <Panel title="Plugins" meta="JSON" hint={<>A telemetria e o perfil são sempre ligados. O worker valida antes de gravar e
            reinicia o plugin na hora. Campos: <code>restock</code> em fase-3-reposicao.md, <code>rank</code> em fase-3b-rank-ligado.md.</>}>
            <div className="stack">
              {!d && loading}
              {d?.plugins.map((p) => (
                <PluginEditor key={p.plugin} accountId={d.account.id} plugin={p.plugin} enabled={p.enabled} config={p.config ?? {}} />
              ))}
              {d && <NewPlugin accountId={d.account.id} existing={d.plugins.map((p) => p.plugin)} />}
            </div>
          </Panel>
          <Panel title="Últimos comandos" flush>
            {!d ? <div className="panel-body">{loading}</div> : (
              <>
                <AutoRefresh active={d.commands.some((c) => c.status === "pending" || c.status === "running")} queryKey={["account", id]} />
                <CommandTable commands={d.commands} nicks={new Map([[d.account.id, d.account.nick]])} />
              </>
            )}
          </Panel>
        </>
      </SectionTabs>
    </>
  );
}
