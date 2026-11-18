import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Todas as hunts do jogo, em ordem de nível. A API do Supabase devolve no máximo 1.000 linhas por pedido e o
 * jogo tem mais que isso (1.048 em 17/11): sem paginar, as hunts mais altas sumiam das listas.
 */
export async function loadAllHunts<T>(supabase: SupabaseClient, cols: string): Promise<{ data: T[]; error: string | null }> {
  const out: T[] = [];
  for (let from = 0; ; from += 1000) {
    const { data, error } = await supabase.from("game_hunts").select(cols).order("level").order("slug").range(from, from + 999);
    if (error) return { data: out, error: error.message };
    out.push(...((data ?? []) as T[]));
    if (!data || data.length < 1000) return { data: out, error: null };
  }
}
