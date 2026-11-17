import { NextResponse } from "next/server";
import { GAME_SITE } from "@/lib/sprites";

/**
 * Retrato de um looktype que não está no atlas do mapa, do jeito que o jogo faz
 * (sprites.mjs: retratoDeLooktype → carregarOutfit): o índice de outfits aponta o manifesto, e o
 * manifesto diz onde está o quadro 1, virado para baixo (direção 3), na folha WebP.
 * Devolve só a posição; o navegador recorta com background-position.
 */
const PACK = "/assets/asset-packs";
const INDEX_TTL = 60 * 60_000;
let index: { at: number; outfits: Record<string, { manifest?: string }> } | null = null;

const localize = (p: string) => p.replace(/^\/assets-packs/, PACK);

async function loadIndex() {
  if (index && Date.now() - index.at < INDEX_TTL) return index.outfits;
  // ~2 MB: fica na memória da função (o cache de fetch do Next não guarda acima de 2 MB)
  const res = await fetch(`${GAME_SITE}${PACK}/outfits-index.json`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
  if (!res.ok) throw new Error(`index ${res.status}`);
  const j = (await res.json()) as { outfits?: Record<string, { manifest?: string }> };
  index = { at: Date.now(), outfits: j.outfits ?? {} };
  return index.outfits;
}

type Manifest = {
  categories?: Record<string, { pages?: { image: string; width: number; height: number }[] }>;
  assets?: Record<string, { frames?: { page?: number; x: number; y: number; w: number; h: number }[] }>;
};

export async function GET(req: Request) {
  const lt = new URL(req.url).searchParams.get("lt") ?? "";
  if (!/^\d{1,6}$/.test(lt)) return NextResponse.json(null, { status: 400 });
  try {
    const entry = (await loadIndex())[lt];
    if (!entry?.manifest) return NextResponse.json(null, { headers: { "Cache-Control": "public, max-age=3600" } });
    const res = await fetch(GAME_SITE + localize(entry.manifest), { next: { revalidate: 86_400 }, signal: AbortSignal.timeout(8000) });
    if (!res.ok) return NextResponse.json(null, { status: 502 });
    const m = (await res.json()) as Manifest;
    const pages = Object.values(m.categories ?? {})[0]?.pages ?? [];
    // nome do arquivo: quadro_?_?_direção.png (o _template é a máscara de cor)
    let best: { frame: number; dir: number; f: { page?: number; x: number; y: number; w: number; h: number } } | null = null;
    for (const [path, a] of Object.entries(m.assets ?? {})) {
      const stem = path.split("/").pop()?.replace(/\.png$/, "") ?? "";
      if (stem.endsWith("_template") || !a.frames?.[0]) continue;
      const n = stem.split("_").map(Number);
      const frame = n[0] || 1, dir = n[3] || 0;
      const score = (dir === 3 ? 0 : 10) + frame;
      if (!best || score < (best.dir === 3 ? 0 : 10) + best.frame) best = { frame, dir, f: a.frames[0] };
    }
    const page = best ? pages[best.f.page ?? 0] : undefined;
    if (!best || !page) return NextResponse.json(null, { headers: { "Cache-Control": "public, max-age=3600" } });
    return NextResponse.json(
      { image: GAME_SITE + localize(page.image), pw: page.width, ph: page.height, x: best.f.x, y: best.f.y, w: best.f.w, h: best.f.h },
      { headers: { "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800" } },
    );
  } catch {
    return NextResponse.json(null, { status: 502 });
  }
}
