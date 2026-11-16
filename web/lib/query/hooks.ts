"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { useQuery, useQueryClient, type QueryKey, type UseQueryOptions } from "@tanstack/react-query";
import { useCallback } from "react";
import { createClient } from "@/lib/supabase/client";
import type { Atlas } from "@/lib/sprites";
import type { Account } from "@/lib/types";

let browserClient: SupabaseClient | null = null;
/** Cliente do Supabase no navegador (a sessão vem dos cookies; o RLS é o mesmo do servidor). */
export function supabaseBrowser(): SupabaseClient {
  browserClient ??= createClient();
  return browserClient;
}

/** Dados de uma página: o carregador roda no navegador e o resultado vai para o cache persistido. */
export function usePanel<T>(
  key: QueryKey,
  load: (sb: SupabaseClient) => Promise<T>,
  opts: Omit<UseQueryOptions<T>, "queryKey" | "queryFn"> = {},
) {
  return useQuery<T>({ queryKey: key, queryFn: () => load(supabaseBrowser()), ...opts });
}

export async function loadAccounts(sb: SupabaseClient): Promise<Account[]> {
  const { data, error } = await sb.from("accounts").select("id, nick, role, enabled, status").order("nick");
  if (error) throw new Error(error.message);
  return (data ?? []) as Account[];
}

/** Contas do usuário: as abas de conta usam em quase toda página. */
export function useAccounts() {
  return usePanel(["accounts"], loadAccounts, { staleTime: 30_000 });
}

/** Atlas dos retratos (pokeidle.io, lido pelo servidor em /api/atlas: o site do jogo não libera CORS). */
export function useAtlas() {
  return useQuery<Atlas | null>({
    queryKey: ["atlas"],
    queryFn: async () => {
      const res = await fetch("/api/atlas");
      return res.ok ? ((await res.json()) as Atlas | null) : null;
    },
    staleTime: 5 * 60_000,
  });
}

/** E-mail de quem entrou, da sessão guardada no navegador (sem ir ao servidor). */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => (await supabaseBrowser().auth.getSession()).data.session?.user.email ?? "",
    staleTime: Infinity,
  });
}

/** Marca tudo como velho e busca de novo o que está na tela (depois de um comando ou de salvar algo). */
export function useRefreshAll() {
  const qc = useQueryClient();
  return useCallback(() => qc.invalidateQueries(), [qc]);
}
