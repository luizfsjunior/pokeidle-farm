"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { supabaseBrowser } from "@/lib/query/hooks";

/**
 * Realtime do Supabase (docs/design/tela-na-hora.md): quando o worker grava o perfil, a estratégia ou
 * um comando de uma conta, as consultas que usam esse dado são buscadas de novo na hora. O RLS vale
 * aqui também: só chegam as mudanças das contas do usuário.
 */
// consultas que mostram o perfil da conta (lib/profile: account_profile)
const PROFILE_QUERIES = new Set(["account", "dex", "dex-all", "boss-profiles", "hunts", "overview"]);

export function RealtimeSync() {
  const qc = useQueryClient();
  useEffect(() => {
    const sb = supabaseBrowser();
    const pending = { profile: new Set<string>(), account: new Set<string>(), commands: false };
    let timer: ReturnType<typeof setTimeout> | null = null;
    const flush = () => {
      timer = null;
      const { profile, account, commands } = pending;
      void qc.invalidateQueries({
        predicate: (q) => {
          const [k, id] = q.queryKey as [string, unknown];
          if (profile.size && PROFILE_QUERIES.has(k)) {
            // por conta quando a chave diz a conta; nas listas de várias contas, sempre
            return typeof id !== "string" || id.includes(",") || profile.has(id) || k === "overview" || k === "hunts";
          }
          if (k === "account" && typeof id === "string" && account.has(id)) return true;
          return commands && k === "commands";
        },
      });
      pending.profile = new Set(); pending.account = new Set(); pending.commands = false;
    };
    // junta as mudanças que chegam juntas (o worker grava várias linhas em sequência)
    const later = () => { if (!timer) timer = setTimeout(flush, 400); };
    const idOf = (p: { new?: unknown; old?: unknown }) =>
      String(((p.new as { account_id?: string } | null)?.account_id) ?? ((p.old as { account_id?: string } | null)?.account_id) ?? "");

    const ch = sb.channel("painel")
      .on("postgres_changes", { event: "*", schema: "public", table: "account_profile" }, (p) => { pending.profile.add(idOf(p)); later(); })
      .on("postgres_changes", { event: "*", schema: "public", table: "strategy_configs" }, (p) => { pending.account.add(idOf(p)); later(); })
      .on("postgres_changes", { event: "*", schema: "public", table: "commands" }, (p) => {
        pending.account.add(idOf(p)); pending.commands = true; later();
      })
      .subscribe();
    return () => { if (timer) clearTimeout(timer); void sb.removeChannel(ch); };
  }, [qc]);
  return null;
}
