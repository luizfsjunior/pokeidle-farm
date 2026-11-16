"use client";

import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect } from "react";

/** Busca de novo os dados da tela (ou só os de `queryKey`) a cada `ms` enquanto `active`. */
export function AutoRefresh({ active, ms = 3000, queryKey }: { active: boolean; ms?: number; queryKey?: QueryKey }) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => qc.invalidateQueries(queryKey ? { queryKey } : undefined), ms);
    return () => clearInterval(t);
  }, [active, ms, qc, queryKey]);
  return null;
}
