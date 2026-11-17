"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AutoRefresh } from "@/components/AutoRefresh";
import { CaptureStatus } from "@/components/Capture";
import { CommandButtons } from "@/components/CommandButtons";
import { CommandTable } from "@/components/CommandTable";
import { HuntPicker } from "@/components/HuntPicker";
import { Ld, LdBlock } from "@/components/Loading";
import { PageHeader, Panel } from "@/components/Page";
import { SectionTabs } from "@/components/SectionTabs";
import { TrainerCard } from "@/components/TrainerCard";
import { TrendChart } from "@/components/TrendChart";
import { activeMon } from "@/lib/profile";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import { loadAccount } from "./data";
import { FocusCard } from "./FocusCard";
import { GemsCard } from "./GemsCard";
import { NewPlugin } from "./NewPlugin";
import { PluginEditor } from "./PluginEditor";
import { ProfileSections } from "./ProfileSections";
import { RankCard } from "./RankCard";

export function AccountView() {
  const { id } = useParams<{ id: string }>();
  const q = usePanel(["account", id], (sb) => loadAccount(sb, id), { refetchInterval: 60_000 });
  const { data: atlas = null } = useAtlas();
  const known = useAccounts().data?.find((a) => a.id === id);
  const d = q.data;
  const account = d?.account ?? known;

  if (q.isSuccess && !d) {
    return <><PageHeader title="Conta" subtitle={<Link href="/">← Todas as contas</Link>} /><p className="muted">Conta não encontrada.</p></>;
  }
  const profile = d?.profile ?? undefined;
  const series = (k: keyof NonNullable<typeof d>["daily"][number]) => (d?.daily ?? []).map((x) => ({ day: x.day, value: x[k] as number | null }));
  const loading = <LdBlock h={220} />;

  return (
    <>
      <PageHeader
        title={account?.nick ?? <Ld w="12ch" />}
        subtitle={<Link href="/">← Todas as contas</Link>}
        actions={account && <CommandButtons account={account} compact />}
      />
      <SectionTabs tabs={[
        { id: "resumo", label: "Resumo" },
        { id: "colecao", label: "Coleção" },
        { id: "estrategia", label: "Estratégia" },
        { id: "ajustes", label: "Ajustes" },
      ]}>
        {/* Resumo */}
        <>
          {!d ? loading : (
            <div className="account-top">
              <TrainerCard account={d.account} profile={profile} atlas={atlas} looktypes={d.looktypes} wide hideNick />
              {profile && <div className="stack"><ProfileSections part="status" profile={profile} atlas={atlas} looktypes={d.looktypes} items={d.items} /></div>}
            </div>
          )}
          {(!d || profile) && (
            <Panel title="Evolução" meta={d && d.daily.length < 2 ? "a linha aparece a partir do 2º dia" : "por dia, até 90 dias"}>
              {!d ? <LdBlock h={160} /> : (
                <div className="trends">
                  <TrendChart title="Nível" points={series("level")} tone="accent" />
                  <TrendChart title="XP" points={series("xp")} tone="diamond" compact />
                  <TrendChart title="Ouro" points={series("gold")} tone="gold" compact />
                  <TrendChart title="Gemas" points={series("gems")} tone="gem" />
                  <TrendChart title="Espécies capturadas" points={series("dex_caught")} tone="good" />
                  <TrendChart title="Pokémons" points={series("pokemon_count")} tone="accent" />
                </div>
              )}
            </Panel>
          )}
        </>

        {/* Equipe e coleção */}
        <>
          {!d ? loading : profile
            ? <ProfileSections part="collection" profile={profile} atlas={atlas} looktypes={d.looktypes} items={d.items} />
            : <p className="muted">Sem perfil ainda: ele aparece uns segundos depois de o worker conectar a conta.</p>}
        </>

        {/* Estratégia */}
        <>
          <Panel title="Captura">
            {!d ? <Ld w="20ch" /> : d.capture
              ? <CaptureStatus accountId={d.account.id} active={d.capture} />
              : <p className="small muted" style={{ margin: 0 }}>Nenhuma. <Link href={`/pokedex?conta=${d.account.id}`}>Escolher na Pokédex →</Link></p>}
          </Panel>
          {!d && loading}
          {d && d.huntOptions.length > 0 && (
            <Panel title="Hunt" hint="Trocar aqui trava a hunt pelo prazo: os plugins gems e rank respeitam até o fim.">
              <HuntPicker key={`${d.hold?.slug}:${profile?.hunt_slug}`} accountId={d.account.id} hunts={d.huntOptions} current={profile?.hunt_slug ?? null} hold={d.hold}
                level={activeMon(profile)?.level ?? null} enabled={d.account.enabled} />
            </Panel>
          )}
          {d && <FocusCard accountId={d.account.id} plugins={d.plugins} />}
          {d?.rank && (
            <>
              <AutoRefresh active ms={30_000} queryKey={["account", id]} />
              <RankCard rank={d.rank} />
            </>
          )}
          {d && <GemsCard plan={d.gemsPlan} potential={d.potential} progress={d.progress} />}
        </>

        {/* Ajustes */}
        <>
          <Panel title="Últimos comandos" flush>
            {!d ? <div className="panel-body">{loading}</div> : (
              <>
                <AutoRefresh active={d.commands.some((c) => c.status === "pending" || c.status === "running")} queryKey={["account", id]} />
                <CommandTable commands={d.commands} nicks={new Map([[d.account.id, d.account.nick]])} />
              </>
            )}
          </Panel>
          <Panel title="Plugins" meta="JSON" hint={<>A telemetria e o perfil são sempre ligados. Campos: <code>restock</code> em
            fase-3-reposicao.md (seção 7), <code>rank</code> em fase-3b-plugin-rank.md e fase-3b-rank-ligado.md. O worker valida
            antes de gravar e reinicia o plugin na hora.</>}>
            <div className="stack">
              {!d && loading}
              {d?.plugins.map((p) => (
                <PluginEditor key={p.plugin} accountId={d.account.id} plugin={p.plugin} enabled={p.enabled} config={p.config ?? {}} />
              ))}
              {d && <NewPlugin accountId={d.account.id} existing={d.plugins.map((p) => p.plugin)} />}
            </div>
          </Panel>
        </>
      </SectionTabs>
    </>
  );
}
