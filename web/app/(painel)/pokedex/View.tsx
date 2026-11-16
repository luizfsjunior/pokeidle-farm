"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import { useSearchParams } from "next/navigation";
import { LdBlock } from "@/components/Loading";
import { AccountTabs, ErrorNote, PageHeader } from "@/components/Page";
import { loadActiveCapture } from "@/lib/capture";
import { loadProfiles } from "@/lib/profile";
import { useAccounts, useAtlas, usePanel } from "@/lib/query/hooks";
import { PokedexGrid, type DexHunt, type DexSpecies } from "./PokedexGrid";

/** Catálogo do jogo: muda só com atualização do jogo. A API devolve no máximo 1.000 linhas por pedido. */
async function loadDexCatalog(supabase: SupabaseClient) {
  const cols = "species_id, name, type1, type2, rarity, hunt_level, evolves_to, evolve_level, stage, looktype:data->looktype";
  const [p1, p2, huntsRes] = await Promise.all([
    supabase.from("game_species").select(cols).order("species_id").range(0, 999),
    supabase.from("game_species").select(cols).order("species_id").range(1000, 1999),
    supabase.from("game_hunts").select("slug, name, level, species_id").order("level"),
  ]);
  return {
    species: [...(p1.data ?? []), ...(p2.data ?? [])] as unknown as DexSpecies[],
    hunts: (huntsRes.data ?? []) as DexHunt[],
    err: p1.error?.message ?? huntsRes.error?.message ?? null,
  };
}

async function loadDexAccount(supabase: SupabaseClient, id: string) {
  const [profiles, capture] = await Promise.all([loadProfiles(supabase, [id]), loadActiveCapture(supabase, id)]);
  return { profile: profiles.get(id) ?? null, capture };
}

/** Pokédex interativa: o catálogo do jogo cruzado com a Pokédex da conta (docs/design/painel-fase-2.md). */
export function PokedexView() {
  const sp = useSearchParams();
  const accountsQ = useAccounts();
  const accounts = accountsQ.data ?? [];
  const chosen = accounts.find((a) => a.id === sp.get("conta")) ?? accounts.find((a) => a.role === "farm") ?? accounts[0] ?? null;
  const catalog = usePanel(["dex-catalog"], loadDexCatalog, { staleTime: 10 * 60_000 }).data;
  const mine = usePanel(["dex", chosen?.id], (sb) => loadDexAccount(sb, chosen!.id), { enabled: !!chosen }).data;
  const { data: atlas = null } = useAtlas();
  const ready = catalog && (mine || (accountsQ.isSuccess && !chosen));

  return (
    <>
      <PageHeader title="Pokédex" subtitle="Todas as espécies do jogo e o que a conta já viu e capturou.">
        <AccountTabs all={false} accounts={accounts} chosen={chosen?.id ?? null} href={(id) => `/pokedex?conta=${id}`} />
      </PageHeader>
      <ErrorNote message={catalog?.err ?? accountsQ.error?.message} />
      {!ready ? (
        <LdBlock h={520} />
      ) : catalog.species.length === 0 ? (
        <p className="muted">O catálogo de espécies ainda não foi gravado: ele aparece depois que o worker conecta.</p>
      ) : (
        <PokedexGrid
          key={chosen?.id}
          species={catalog.species}
          hunts={catalog.hunts}
          dex={mine?.profile?.pokedex ?? {}}
          atlas={atlas}
          hasProfile={!!mine?.profile}
          accountId={chosen?.role === "farm" ? chosen.id : null}
          capture={mine?.capture ?? null}
          balls={mine?.profile?.balls}
        />
      )}
    </>
  );
}
