import Link from "next/link";
import { notFound } from "next/navigation";
import { AutoRefresh } from "@/components/AutoRefresh";
import { CommandButtons } from "@/components/CommandButtons";
import { CommandTable } from "@/components/CommandTable";
import { Shell } from "@/components/Shell";
import { rankSummary } from "@/lib/rank";
import { requireUser } from "@/lib/supabase/server";
import { STATUS_LABEL, type Account, type Command } from "@/lib/types";
import { FocusCard } from "./FocusCard";
import { NewPlugin } from "./NewPlugin";
import { PluginEditor } from "./PluginEditor";
import { GemsCard, type GemsPlanData, type GemsPotentialData, type ProgressPlanData } from "./GemsCard";
import { RankCard } from "./RankCard";

export const dynamic = "force-dynamic";

export default async function AccountPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { supabase, email } = await requireUser();
  const { data: account } = await supabase
    .from("accounts").select("id, nick, role, enabled, status").eq("id", id).maybeSingle<Account>();
  if (!account) notFound();

  const [configs, cmds] = await Promise.all([
    supabase.from("strategy_configs").select("plugin, enabled, config").eq("account_id", id).order("plugin"),
    supabase.from("commands").select("*").eq("account_id", id).order("created_at", { ascending: false }).limit(20),
  ]);
  const plugins = (configs.data ?? []) as { plugin: string; enabled: boolean; config: Record<string, unknown> }[];
  const commands = (cmds.data ?? []) as Command[];
  const rankOn = plugins.some((p) => p.plugin === "rank" && p.enabled);
  const rank = rankOn ? await rankSummary(supabase, account.id) : null;
  const gemsOn = plugins.some((p) => p.plugin === "gems" && p.enabled);
  const [gemsPlanRes, potentialRes, progressRes] = await Promise.all([
    gemsOn
      ? supabase.from("events").select("received_at, data").eq("account_id", id).eq("type", "gems.plan")
          .order("received_at", { ascending: false }).limit(1).maybeSingle()
      : Promise.resolve({ data: null }),
    supabase.from("events").select("received_at, data").eq("account_id", id).eq("type", "gems.potential")
      .order("received_at", { ascending: false }).limit(1).maybeSingle(),
    gemsOn
      ? supabase.from("events").select("received_at, data").eq("account_id", id).eq("type", "progress.plan")
          .order("received_at", { ascending: false }).limit(1).maybeSingle()
      : Promise.resolve({ data: null }),
  ]);
  const progress = progressRes.data
    ? { at: progressRes.data.received_at as string, ...(progressRes.data.data as Omit<ProgressPlanData, "at">) }
    : null;
  const gemsPlan = gemsPlanRes.data
    ? { at: gemsPlanRes.data.received_at as string, ...(gemsPlanRes.data.data as Omit<GemsPlanData, "at">) }
    : null;
  const potential = potentialRes.data
    ? { at: potentialRes.data.received_at as string, ...(potentialRes.data.data as Omit<GemsPotentialData, "at">) }
    : null;

  return (
    <Shell email={email}>
      <p className="small"><Link href="/">← Visão geral</Link></p>
      <div className="spread">
        <h1>{account.nick}</h1>
        <span className={`badge ${account.status}`}>{STATUS_LABEL[account.status] ?? account.status}</span>
      </div>
      <div className="stack">
        <section className="card">
          <h2>Sessão</h2>
          <p className="muted small" style={{ margin: 0 }}>{account.enabled ? "Ligada" : "Desligada"} · {account.role === "farm" ? "farm" : "pessoal"}</p>
          <CommandButtons account={account} />
        </section>

        <FocusCard accountId={account.id} plugins={plugins} />
        {rank && (
          <>
            <AutoRefresh active ms={30_000} />
            <RankCard rank={rank} />
          </>
        )}

        <GemsCard plan={gemsPlan} potential={potential} progress={progress} />

        <details className="card">
          <summary><strong>Avançado: plugins em JSON</strong></summary>
          <div className="stack" style={{ marginTop: ".75rem" }}>
        <h2 style={{ margin: ".5rem 0 0" }}>Plugins</h2>
        <p className="muted small" style={{ margin: 0 }}>
          A telemetria é sempre ligada e não aparece aqui. Os campos do <code>restock</code> estão em
          docs/design/fase-3-reposicao.md, seção 7; os do <code>rank</code>, em docs/design/fase-3b-plugin-rank.md, seção 1, e
          docs/design/fase-3b-rank-ligado.md, seção 8.
        </p>
        {plugins.map((p) => (
          <PluginEditor key={p.plugin} accountId={account.id} plugin={p.plugin} enabled={p.enabled} config={p.config ?? {}} />
        ))}
        <NewPlugin accountId={account.id} existing={plugins.map((p) => p.plugin)} />
          </div>
        </details>

        <section className="card">
          <h2>Últimos comandos</h2>
          <AutoRefresh active={commands.some((c) => c.status === "pending" || c.status === "running")} />
          <CommandTable commands={commands} nicks={new Map([[account.id, account.nick]])} />
        </section>
      </div>
    </Shell>
  );
}
