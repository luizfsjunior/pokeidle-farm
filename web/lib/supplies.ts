import { activeMon, type Profile } from "./profile";

/** Poções e revives da loja do NPC (lib/shop.ts, SHOP_ITEMS). */
const POTION_IDS = [200, 201, 202, 203, 204, 70070];
const REVIVE_IDS = [205, 206];

const sumIds = (bag: Record<string, number> | undefined, ids: number[]) =>
  ids.reduce((s, id) => s + (Number(bag?.[String(id)]) || 0), 0);

/** O que a conta tem para continuar farmando: HP do ativo, poções, revives e bolas (do perfil, a cada 2 min). */
export function supplies(p: Profile | undefined) {
  if (!p) return null;
  const mon = activeMon(p);
  const hpPct = mon?.hp != null && mon.max_hp ? Math.max(0, Math.min(1, mon.hp / mon.max_hp)) : null;
  return {
    hpPct,
    potions: sumIds(p.items, POTION_IDS),
    revives: sumIds(p.items, REVIVE_IDS),
    balls: Object.values(p.balls ?? {}).reduce((s, n) => s + (Number(n) || 0), 0),
  };
}

/**
 * Horas de farm até o próximo nível do treinador, no ritmo medido (XP por hora ativa). Sem ritmo ou sem os
 * limites do nível no perfil, null.
 */
export function hoursToLevel(p: Profile | undefined, xpPerHour: number | null): number | null {
  if (!p || p.xp == null || p.xp_next == null || !xpPerHour || xpPerHour <= 0) return null;
  const left = p.xp_next - p.xp;
  return left > 0 ? left / xpPerHour : 0;
}

/** "45 min", "3,2 h" ou "2,5 dias" (de farm). */
export function farmTime(h: number | null): string {
  if (h == null) return "—";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${(Math.round(h * 10) / 10).toLocaleString("pt-BR")} h`;
  return `${(Math.round((h / 24) * 10) / 10).toLocaleString("pt-BR")} dias`;
}
