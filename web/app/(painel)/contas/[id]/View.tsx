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
import { IncubatorCard } from "./IncubatorCard";
import { MarketCard } from "./MarketCard";
import { NowCard } from "./NowCard";
import { OutlandCard } from "./OutlandCard";
import { PlanCard } from "./PlanCard";
import { pluginRows } from "@/lib/plugins";
import { PluginEditor } from "./PluginEditor";
import { NotifierEditor } from "./NotifierEditor";
import { ProfileSections } from "./ProfileSections";
import { Collection } from "./Collection";
import { RankCard } from "./RankCard";
import { ShopCard } from "./ShopCard";

/**
 * Página da conta em 4 abas (docs/design/painel-ux-v2.md, seção 3, e refatoracao-2026-11-20.md, 4): Agora (modo,
 * desvio, plano e alertas), Pokémons (a lista, a montagem da equipe), Itens (mochila, loja e Mercado) e Ajustes.
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
        { id: "itens", label: "Itens" },
        { id: "ajustes", label: "Ajustes" },
      ]}>
        {/* Agora */}
        <>
          {!d ? loading : (
            <TrainerCard account={d.account} profile={profile} atlas={atlas} looktypes={d.looktypes} wide hideNick
              switchActive={{ training: d.plugins.some((p) => p.plugin === "team_train" && p.enabled) }} />
          )}
          {d && (
            <NowCard accountId={d.account.id} plugins={d.plugins} capture={d.capture} hold={d.hold} hunts={d.huntOptions}
              huntSlug={profile?.hunt_slug ?? null} trainerLevel={profile?.level ?? null} enabled={d.account.enabled}
              team={profile?.team ?? []} activeId={profile?.active_pokemon_id ?? null} alerts={d.alerts} />
          )}
          {d && <PlanCard plan={d.gemsPlan} progress={d.progress} huntSlug={profile?.hunt_slug ?? null} hold={d.hold}
            capture={d.capture} />}
          {d?.outland && <OutlandCard data={d.outland} progress={d.progress} />}
          {d?.rank && (
            <>
              <AutoRefresh active ms={30_000} queryKey={["account", id]} />
              <RankCard rank={d.rank} />
            </>
          )}
          {d && profile && (
            <Fold title="Bônus e passe">
              <ProfileSections part="status" profile={profile} items={d.items} />
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
            ? <>
                <Collection accountId={d.account.id} profile={profile} atlas={atlas} looktypes={d.looktypes}
                  training={d.plugins.some((p) => p.plugin === "team_train" && p.enabled)} />
              </>
            : <p className="muted">Sem perfil ainda: ele aparece uns segundos depois de o worker conectar a conta.</p>}
        </>

        {/* Itens */}
        <>
          {!d ? loading : profile
            ? <>
                <ProfileSections part="bag" profile={profile} items={d.items} restock={restockItems(d.plugins)} />
                <ShopCard accountId={d.account.id} profile={profile} />
                <IncubatorCard accountId={d.account.id} profile={profile} />
                <MarketCard accountId={d.account.id} profile={profile} items={d.items}
                  sellerActive={d.plugins.some((p) => p.plugin === "seller" && p.enabled && p.config.dry_run === false)} />
              </>
            : <p className="muted">Sem perfil ainda.</p>}
        </>

        {/* Ajustes */}
        <>
          <Panel title="Plugins" hint={<>A telemetria, o perfil e a vigia são sempre ligados. Modo, desvio e treino se ajustam na aba
            Agora; aqui é para ligar ou desligar à mão. O worker valida a config antes de gravar e reinicia o plugin na hora.</>}>
            <div className="stack">
              {!d && loading}
              {d && pluginRows(d.plugins).map((p) => p.plugin === "notifier"
                ? <NotifierEditor key={p.plugin} accountId={d.account.id} config={p.config} />
                : <PluginEditor key={p.plugin} accountId={d.account.id} plugin={p.plugin} enabled={p.enabled} config={p.config} />)}
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

/** As regras do restock (mínimo e alvo por item), para a mochila mostrar o que é reposto. */
function restockItems(plugins: { plugin: string; config: Record<string, unknown> }[]) {
  const items = plugins.find((p) => p.plugin === "restock")?.config.items;
  return Array.isArray(items) ? (items as { id: number; min?: number; target?: number }[]) : [];
}
