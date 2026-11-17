import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Imagens do próprio jogo (arquivos públicos de pokeidle.io), como o cliente oficial usa:
 * - retratos dos pokémons: um atlas (PNG) indexado por `looktype`, descrito em marker-atlas.json;
 * - ícones de itens: o caminho `icon` do catálogo, relativo a /assets.
 * O atlas muda a cada atualização do jogo; por isso o JSON é relido a cada 5 min e a imagem leva `?v=`.
 */
export const GAME_SITE = "https://pokeidle.io";
const ATLAS_JSON = `${GAME_SITE}/assets/site/assets/maps/marker-atlas.json`;

export type Atlas = { cols: number; rows: number; image: string; slots: Record<string, [number, number]> };

export async function loadAtlas(): Promise<Atlas | null> {
  try {
    const res = await fetch(ATLAS_JSON, { next: { revalidate: 300 }, signal: AbortSignal.timeout(5000) });
    if (!res.ok) return null;
    const j = (await res.json()) as Record<string, unknown>;
    const slots = j.slots as Atlas["slots"] | undefined;
    if (!slots || typeof slots !== "object") return null;
    let image = typeof j.image === "string" ? j.image : "/assets/site/assets/maps/marker-atlas.png";
    const version = j.version != null ? String(j.version) : "";
    if (version && !image.includes("v=")) image += `${image.includes("?") ? "&" : "?"}v=${encodeURIComponent(version)}`;
    return {
      cols: Number(j.cols) || 16,
      rows: Number(j.rows) || 1,
      image: image.startsWith("http") ? image : GAME_SITE + image,
      slots,
    };
  } catch {
    return null; // sem atlas o painel mostra uma pokébola no lugar
  }
}

/** looktype por espécie, da Pokedex gravada pelo worker (`game_species.data.looktype`). */
export async function speciesLooktypes(supabase: SupabaseClient, ids: number[]): Promise<Map<number, number>> {
  if (ids.length === 0) return new Map();
  const { data } = await supabase.from("game_species").select("species_id, looktype:data->looktype").in("species_id", ids);
  const out = new Map<number, number>();
  for (const r of (data ?? []) as { species_id: number; looktype: unknown }[]) {
    const lt = Number(r.looktype);
    if (Number.isFinite(lt) && lt > 1) out.set(Number(r.species_id), lt);
  }
  return out;
}

/**
 * URL absoluta de um ícone de item do jogo. O catálogo traz dois formatos (conferidos em 16/11):
 * caminho a partir da raiz (`/img/itens/x.png`) ou só o arquivo (`leaf_stone.gif`), que fica em
 * /assets/site/assets/items/.
 */
export function itemIconUrl(icon: string | null | undefined): string | null {
  if (!icon) return null;
  if (icon.startsWith("http")) return icon;
  if (icon.startsWith("/")) return GAME_SITE + icon;
  return GAME_SITE + (icon.includes("/") ? `/assets/${icon}` : `/assets/site/assets/items/${icon}`);
}

/** Ícones das bolas da loja (não vêm no catálogo de itens). */
export const BALL_ICONS: Record<string, string> = {
  "1": "/assets/site/assets/ui/ball-poke.png",
  "2": "/assets/site/assets/ui/ball-great.png",
  "3": "/img/ball-super.png",
  "4": "/assets/site/assets/ui/ball-ultra.png",
  "5": "/img/ball-beast.png",
};
export const BALL_NAMES: Record<string, string> = {
  "1": "Poké Ball", "2": "Great Ball", "3": "Super Ball", "4": "Ultra Ball", "5": "Beast Ball",
};
