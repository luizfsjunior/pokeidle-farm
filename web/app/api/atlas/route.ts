import { NextResponse } from "next/server";
import { loadAtlas } from "@/lib/sprites";

/** Atlas dos retratos do jogo para o navegador (o site do jogo não libera CORS). Cache de 5 min. */
export async function GET() {
  const atlas = await loadAtlas();
  return NextResponse.json(atlas, {
    headers: { "Cache-Control": "private, max-age=300, stale-while-revalidate=3600" },
  });
}
