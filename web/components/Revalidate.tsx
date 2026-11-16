"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

const STALE_MS = 5_000; // mais velho que isso: busca de novo por baixo
const FOCUS_MS = 60_000; // ao voltar para a aba depois de um minuto

/**
 * Stale-while-revalidate das páginas do servidor (docs/design/painel-swr.md). Quando a página veio do
 * cache do navegador (renderizada há mais de alguns segundos), mostra o que tem e pede a versão nova
 * com router.refresh(): a tela antiga fica até a nova chegar, sem esqueleto. Também atualiza ao voltar
 * para a aba ou para o app.
 */
export function Revalidate({ at }: { at: number }) {
  const router = useRouter();
  useEffect(() => {
    if (Date.now() - at > STALE_MS) router.refresh();
  }, [at, router]);
  useEffect(() => {
    const onShow = () => {
      if (document.visibilityState === "visible" && Date.now() - at > FOCUS_MS) router.refresh();
    };
    document.addEventListener("visibilitychange", onShow);
    return () => document.removeEventListener("visibilitychange", onShow);
  }, [at, router]);
  return null;
}
