"use client";

import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { useState } from "react";
import { RealtimeSync } from "./realtime";

/**
 * Cache dos dados do painel no navegador (docs/design/painel-swr.md): cada página mostra na hora o que
 * já tem guardado e busca a versão nova por baixo (stale-while-revalidate). O cache fica no
 * localStorage, então sobrevive a fechar e abrir o app.
 */
export const CACHE_KEY = "pf-cache-v1";
// cada deploy apaga o cache guardado: um carregador novo não lê dado no formato antigo (17/11, a
// seção Captura sumia porque as regras do jogo vinham do cache de antes do deploy)
const BUSTER = process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA ?? "1";
const DAY = 86_400_000;

// o JSON não guarda Map nem Set, que os carregadores usam bastante: viram { __map } / { __set }
function replacer(_k: string, v: unknown) {
  if (v instanceof Map) return { __map: [...v] };
  if (v instanceof Set) return { __set: [...v] };
  return v;
}
function reviver(_k: string, v: unknown) {
  if (v && typeof v === "object") {
    const o = v as { __map?: unknown; __set?: unknown };
    if (Array.isArray(o.__map)) return new Map(o.__map as [unknown, unknown][]);
    if (Array.isArray(o.__set)) return new Set(o.__set);
  }
  return v;
}

function storage(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const s = window.localStorage;
    s.getItem(CACHE_KEY); // aba anônima ou site bloqueado: lança aqui
    return s;
  } catch {
    return undefined;
  }
}

/** Some com o cache (ao sair da conta). */
export function clearCache() {
  try { storage()?.removeItem(CACHE_KEY); } catch { /* sem localStorage */ }
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000, // ao abrir a página de novo, mostra o cache e busca por baixo
        gcTime: DAY,
        refetchOnWindowFocus: true,
        retry: 1,
      },
    },
  }));
  const [persister] = useState(() => createSyncStoragePersister({
    storage: storage(),
    key: CACHE_KEY,
    throttleTime: 1_000,
    serialize: (d) => JSON.stringify(d, replacer),
    deserialize: (s) => JSON.parse(s, reviver),
  }));
  return (
    // buster: muda quando o formato dos dados guardados muda. O cache é apagado ao entrar e ao sair
    // (login/page.tsx e o botão Sair), para não mostrar dados de outro usuário no mesmo aparelho.
    <PersistQueryClientProvider client={client} persistOptions={{ persister, maxAge: DAY, buster: BUSTER }}>
      <RealtimeSync />
      {children}
    </PersistQueryClientProvider>
  );
}
