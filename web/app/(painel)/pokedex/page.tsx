import { AccountTabs, ErrorNote, PageHeader } from "@/components/Page";
import { Shell } from "@/components/Shell";
import { loadActiveCapture } from "@/lib/capture";
import { loadProfiles } from "@/lib/profile";
import { loadAtlas } from "@/lib/sprites";
import { requireUser } from "@/lib/supabase/server";
import type { Account } from "@/lib/types";
import { PokedexGrid, type DexHunt, type DexSpecies } from "./PokedexGrid";

export const dynamic = "force-dynamic";

/** Pokédex interativa: o catálogo do jogo cruzado com a Pokédex da conta (docs/design/painel-fase-2.md). */
export default async function PokedexPage({ searchParams }: { searchParams: Promise<{ conta?: string }> }) {
  const { conta } = await searchParams;
  const { supabase, email } = await requireUser();

  const accountsRes = await supabase.from("accounts").select("id, nick, role, enabled, status").order("nick");
  const accounts = (accountsRes.data ?? []) as Account[];
  const chosen = accounts.find((a) => a.id === conta) ?? accounts.find((a) => a.role === "farm") ?? accounts[0] ?? null;

  // a API devolve no máximo 1.000 linhas por pedido: a Pokédex tem ~1.300
  const cols = "species_id, name, type1, type2, rarity, hunt_level, evolves_to, evolve_level, stage, looktype:data->looktype";
  const [p1, p2, huntsRes, profiles, atlas] = await Promise.all([
    supabase.from("game_species").select(cols).order("species_id").range(0, 999),
    supabase.from("game_species").select(cols).order("species_id").range(1000, 1999),
    supabase.from("game_hunts").select("slug, name, level, species_id").order("level"),
    loadProfiles(supabase, chosen ? [chosen.id] : []),
    loadAtlas(),
  ]);
  const species = [...(p1.data ?? []), ...(p2.data ?? [])] as unknown as DexSpecies[];
  const capture = chosen ? await loadActiveCapture(supabase, chosen.id) : null;
  const hunts = (huntsRes.data ?? []) as DexHunt[];
  const profile = chosen ? profiles.get(chosen.id) : undefined;
  const err = accountsRes.error?.message ?? p1.error?.message ?? huntsRes.error?.message;

  return (
    <Shell email={email}>
      <PageHeader title="Pokédex" subtitle="Todas as espécies do jogo e o que a conta já viu e capturou.">
        <AccountTabs all={false} accounts={accounts} chosen={chosen?.id ?? null} href={(id) => `/pokedex?conta=${id}`} />
      </PageHeader>
      <ErrorNote message={err} />
      {species.length === 0 ? (
        <p className="muted">O catálogo de espécies ainda não foi gravado: ele aparece depois que o worker conecta.</p>
      ) : (
        <PokedexGrid
          species={species}
          hunts={hunts}
          dex={profile?.pokedex ?? {}}
          atlas={atlas}
          hasProfile={!!profile}
          accountId={chosen?.role === "farm" ? chosen.id : null}
          capture={capture}
          balls={profile?.balls}
        />
      )}
    </Shell>
  );
}
