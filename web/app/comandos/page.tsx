import { AutoRefresh } from "@/components/AutoRefresh";
import { CommandTable } from "@/components/CommandTable";
import { Shell } from "@/components/Shell";
import { requireUser } from "@/lib/supabase/server";
import type { Command } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function CommandsPage() {
  const { supabase, email } = await requireUser();
  const [cmds, accounts] = await Promise.all([
    supabase.from("commands").select("*").order("created_at", { ascending: false }).limit(100),
    supabase.from("accounts").select("id, nick"),
  ]);
  const commands = (cmds.data ?? []) as Command[];
  const nicks = new Map((accounts.data ?? []).map((a) => [a.id as string, a.nick as string]));
  const active = commands.some((c) => c.status === "pending" || c.status === "running");

  return (
    <Shell email={email}>
      <h1>Comandos</h1>
      <p className="secondary small">
        Os últimos 100. O worker busca os pendentes a cada 5 s; um comando que não é pego em 5 min expira.
      </p>
      {cmds.error && <p className="error">{cmds.error.message}</p>}
      <AutoRefresh active={active} />
      <div className="card"><CommandTable commands={commands} nicks={nicks} /></div>
    </Shell>
  );
}
