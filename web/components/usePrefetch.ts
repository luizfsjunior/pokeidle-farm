"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";

/**
 * Busca a página inteira quando o dedo ou o mouse chega no link (antes do clique), e ela entra no cache
 * do navegador por 10 min (staleTimes). Assim até a primeira visita a uma página do menu abre rápido.
 * Ver docs/design/painel-swr.md.
 */
export function usePrefetch() {
  const router = useRouter();
  return useCallback((href: string) => () => router.prefetch(href), [router]);
}
