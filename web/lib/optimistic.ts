import type { QueryClient } from "@tanstack/react-query";
import type { Mon, Profile } from "@/lib/profile";
import type { CommandType } from "@/lib/types";

/**
 * Tela na hora (docs/design/tela-na-hora.md): quando um comando termina como "feito", o painel já
 * mostra o efeito previsível dele no cache, sem esperar o worker gravar o perfil. O dado real chega
 * logo depois (Realtime) e substitui este.
 */

type Obj = Record<string, unknown>;
const isProfile = (v: unknown, id: string): v is Profile =>
  !!v && typeof v === "object" && (v as Obj).account_id === id && Array.isArray((v as Obj).team);

/** Copia só o caminho até os perfis da conta e aplica `fn` neles (o resto do cache fica igual). */
function mapProfiles(v: unknown, id: string, fn: (p: Profile) => Profile, depth = 0): unknown {
  if (depth > 6 || v == null || typeof v !== "object") return v;
  if (isProfile(v, id)) return fn(v);
  if (v instanceof Map) {
    let changed = false;
    const out = new Map();
    for (const [k, x] of v) { const y = mapProfiles(x, id, fn, depth + 1); changed ||= y !== x; out.set(k, y); }
    return changed ? out : v;
  }
  if (Array.isArray(v)) {
    // listas grandes (catálogos) não têm perfil dentro
    if (v.length > 200) return v;
    let changed = false;
    const out = v.map((x) => { const y = mapProfiles(x, id, fn, depth + 1); changed ||= y !== x; return y; });
    return changed ? out : v;
  }
  let changed = false;
  const out: Obj = {};
  for (const [k, x] of Object.entries(v as Obj)) { const y = mapProfiles(x, id, fn, depth + 1); changed ||= y !== x; out[k] = y; }
  return changed ? out : v;
}

function moveInTeam(p: Profile, pokemonId: number, slot: number | null): Profile {
  const all = new Map<number, Mon>();
  for (const m of [...p.top_pokemon, ...p.shinies, ...p.team]) all.set(m.id, m);
  const mon = all.get(pokemonId);
  const team = p.team.filter((m) => m.id !== pokemonId);
  if (slot != null && mon) team.push({ ...mon, slot });
  team.sort((a, b) => (a.slot ?? 99) - (b.slot ?? 99));
  const setSlot = (m: Mon) => (m.id === pokemonId ? { ...m, slot } : m);
  return { ...p, team, top_pokemon: p.top_pokemon.map(setSlot), shinies: p.shinies.map(setSlot) };
}

function profilePatch(type: CommandType, params: Obj): ((p: Profile) => Profile) | null {
  const pid = Number(params.pokemon_id);
  switch (type) {
    case "team.active":
      return Number.isFinite(pid) ? (p) => ({ ...p, active_pokemon_id: pid }) : null;
    case "team.move":
      return Number.isFinite(pid) ? (p) => moveInTeam(p, pid, params.slot == null ? null : Number(params.slot)) : null;
    case "hunt.select":
      return typeof params.slug === "string" ? (p) => ({ ...p, hunt_slug: params.slug as string }) : null;
    default:
      return null;
  }
}

/** Comandos que mudam o perfil: o painel espera o Realtime em vez de buscar o perfil velho. */
export const PROFILE_COMMANDS: CommandType[] = ["team.active", "team.move", "hunt.select"];

/** Aplica o efeito de um comando feito no cache. Devolve true se mudou algo. */
export function applyOptimistic(qc: QueryClient, accountId: string, type: CommandType, params: Obj): boolean {
  let touched = false;
  const fn = profilePatch(type, params);
  if (fn) {
    for (const q of qc.getQueryCache().getAll()) {
      const before = q.state.data;
      const after = mapProfiles(before, accountId, fn);
      if (after !== before) { qc.setQueryData(q.queryKey, after); touched = true; }
    }
  }
  if (type === "plugin.set" && typeof params.plugin === "string") {
    qc.setQueryData(["account", accountId], (d: unknown) => {
      const data = d as { plugins?: { plugin: string; enabled: boolean; config: Obj }[] } | undefined;
      if (!data?.plugins) return d;
      // sem config no comando, o worker mantém a de antes (ligar/desligar pela aba Ajustes)
      const old = data.plugins.find((p) => p.plugin === params.plugin);
      const row = {
        plugin: params.plugin as string,
        enabled: typeof params.enabled === "boolean" ? params.enabled : old?.enabled ?? true,
        config: (params.config as Obj | undefined) ?? old?.config ?? {},
      };
      const plugins = old
        ? data.plugins.map((p) => (p.plugin === row.plugin ? { ...p, ...row } : p))
        : [...data.plugins, row];
      touched = true;
      return { ...data, plugins };
    });
  }
  return touched;
}
