"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { useSearchParams } from "next/navigation";
import { LdBlock } from "@/components/Loading";
import { AccountPicker } from "@/components/AccountPicker";
import { ErrorNote, PageHeader } from "@/components/Page";
import { loadActiveCapture } from "@/lib/capture";
import { loadAllHunts } from "@/lib/catalog";
import { loadProfiles } from "@/lib/profile";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import { PokedexGrid, type DexHunt, type DexSpecies } from "./PokedexGrid";

/** Catálogo do jogo: muda só com atualização do jogo. A API devolve no máximo 1.000 linhas por pedido. */
async function loadDexCatalog(supabase: SupabaseClient) {
  const cols = "species_id, name, type1, type2, rarity, hunt_level, evolves_to, evolve_level, stage, looktype:data->looktype";
  const [p1, p2, huntsRes] = await Promise.all([
    supabase.from("game_species").select(cols).order("species_id").range(0, 999),
    supabase.from("game_species").select(cols).order("species_id").range(1000, 1999),
    loadAllHunts<DexHunt>(supabase, "slug, name, level, species_id, region"),
  ]);
  return {
    species: [...(p1.data ?? []), ...(p2.data ?? [])] as unknown as DexSpecies[],
    hunts: huntsRes.data,
    err: p1.error?.message ?? huntsRes.error ?? null,
  };
}

type DexEntry = { c?: number; k?: number } | number;

async function loadDexAccount(supabase: SupabaseClient, id: string) {
  const [profiles, capture] = await Promise.all([loadProfiles(supabase, [id]), loadActiveCapture(supabase, id)]);
  const profile = profiles.get(id) ?? null;
  return { dex: profile?.pokedex ?? null, updated: profile?.updated_at ?? null, balls: profile?.balls, capture, level: profile?.level ?? null };
}

/** As Pokédex de todas as contas juntas: capturas e abates somados por espécie. */
async function loadDexAll(supabase: SupabaseClient, ids: string[]) {
  const profiles = await loadProfiles(supabase, ids);
  const dex: Record<string, DexEntry> = {};
  let updated: string | null = null;
  for (const p of profiles.values()) {
    if (!updated || p.updated_at > updated) updated = p.updated_at;
    for (const [k, e] of Object.entries(p.pokedex ?? {})) {
      const c = typeof e === "number" ? e : e?.c ?? 0;
      const kills = typeof e === "object" && e ? e.k ?? 0 : 0;
      const cur = dex[k];
      const cc = cur == null ? 0 : typeof cur === "number" ? cur : cur.c ?? 0;
      const ck = cur != null && typeof cur === "object" ? cur.k ?? 0 : 0;
      dex[k] = { c: cc + c, k: ck + kills };
    }
  }
  return { dex: profiles.size ? dex : null, updated, balls: undefined, capture: null, level: null };
}

/** Pokédex interativa: o catálogo do jogo cruzado com a Pokédex da conta (docs/design/painel-fase-2.md). */
export function PokedexView() {
  const sp = useSearchParams();
  const accountsQ = useAccounts();
  const accounts = accountsQ.data ?? [];
  const together = sp.get("conta") === "todas";
  const chosen = together ? null : accounts.find((a) => a.id === sp.get("conta")) ?? accounts.find((a) => a.role === "farm") ?? accounts[0] ?? null;
  const ids = accounts.map((a) => a.id);
  const catalog = usePanel(["dex-catalog"], loadDexCatalog, { staleTime: 10 * 60_000 }).data;
  // o worker grava o perfil a cada ~2 min: a página busca de novo a cada minuto
  const one = usePanel(["dex", chosen?.id], (sb) => loadDexAccount(sb, chosen!.id), { enabled: !!chosen, refetchInterval: 60_000 }).data;
  const all = usePanel(["dex-all", ids.join(",")], (sb) => loadDexAll(sb, ids), { enabled: together && ids.length > 0, refetchInterval: 60_000 }).data;
  const mine = together ? all : one;
  const { data: atlas = null } = useAtlas();
  const ready = catalog && (mine || (accountsQ.isSuccess && !chosen && !together));

  return (
    <>
      <PageHeader title="Pokédex">
        <AccountPicker accounts={accounts} chosen={chosen?.id ?? null} hasParam={sp.has("conta")} href={(id) => `/pokedex?conta=${id ?? "todas"}`} />
      </PageHeader>
      <ErrorNote message={catalog?.err ?? accountsQ.error?.message} />
      {!ready ? (
        <LdBlock h={520} />
      ) : catalog.species.length === 0 ? (
        <p className="muted">O catálogo de espécies ainda não foi gravado: ele aparece depois que o worker conecta.</p>
      ) : (
        <PokedexGrid
          key={chosen?.id ?? "todas"}
          species={catalog.species}
          hunts={catalog.hunts}
          dex={mine?.dex ?? {}}
          atlas={atlas}
          hasProfile={!!mine?.dex}
          together={together}
          updatedAt={mine?.updated ?? null}
          accountId={chosen?.role === "farm" ? chosen.id : null}
          level={mine?.level ?? null}
          capture={mine?.capture ?? null}
          balls={mine?.balls}
        />
      )}
    </>
  );
}
