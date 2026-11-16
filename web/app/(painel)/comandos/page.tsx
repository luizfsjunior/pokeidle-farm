"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { AutoRefresh } from "@/components/AutoRefresh";
import { CommandTable } from "@/components/CommandTable";
import { LdRows } from "@/components/Loading";
import { ErrorNote, PageHeader, Panel } from "@/components/Page";
import { usePanel } from "@/lib/query/hooks";
import type { Command } from "@/lib/types";

async function loadCommands(supabase: SupabaseClient) {
  const [cmds, accounts] = await Promise.all([
    supabase.from("commands").select("*").order("created_at", { ascending: false }).limit(100),
    supabase.from("accounts").select("id, nick"),
  ]);
  return {
    commands: (cmds.data ?? []) as Command[],
    nicks: new Map((accounts.data ?? []).map((a) => [a.id as string, a.nick as string])),
    err: cmds.error?.message ?? null,
  };
}

/** Estática: os dados vêm no navegador, com cache (lib/query). */
export default function CommandsPage() {
  const { data: d } = usePanel(["commands"], loadCommands);
  const active = !!d?.commands.some((c) => c.status === "pending" || c.status === "running");
  return (
    <>
      <PageHeader title="Comandos" subtitle="Os últimos 100. O worker busca os pendentes a cada 5 s; um comando que não é pego em 5 min expira." />
      <ErrorNote message={d?.err} />
      <AutoRefresh active={active} queryKey={["commands"]} />
      <Panel title="Histórico" flush>
        {d ? <CommandTable commands={d.commands} nicks={d.nicks} /> : (
          <table><tbody><LdRows cols={6} rows={6} /></tbody></table>
        )}
      </Panel>
    </>
  );
}
