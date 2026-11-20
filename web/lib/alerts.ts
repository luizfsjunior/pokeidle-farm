import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Alertas da conta (docs/design/refatoracao-2026-11-20.md, 4.1): o que quer atenção agora. Em 20/11 a conta
 * gastou ~1,4 M de ouro em revives numa hora e a pessoal ficou o dia em −127 mil/h sem ninguém ver.
 */
export type Alert = { account_id: string; level: "critical" | "warning"; text: string; at: string };

const WINDOW_H = 2;
const EVENT_TEXT: Record<string, (d: Record<string, unknown>) => { level: Alert["level"]; text: string }> = {
  "watchdog.revive_storm": (d) => ({
    level: "critical",
    text: `Morrendo em loop em ${d.hunt_slug ?? "?"} (${d.revives ?? "?"} revives em 3 min): a vigia voltou o ativo para o mais forte`,
  }),
  "watchdog.dangerous_hunt": (d) => ({ level: "warning", text: `Mortes repetidas em ${d.hunt_slug ?? "?"}` }),
  "watchdog.no_kills": (d) => ({ level: "warning", text: `Sem abates há ${d.minutes ?? "?"} min em ${d.hunt_slug ?? "?"}` }),
  "watchdog.no_items": (d) => ({ level: "critical", text: `Sem poção ou revive: parada em ${d.hunt_slug ?? "?"}` }),
  "team_train.waiting_hunt": (d) => ({
    level: "warning",
    text: `Treino esperando uma hunt segura para o pokémon ${d.pokemon_id ?? "?"} (está em ${d.hunt_slug ?? "?"})`,
  }),
};

export async function loadAlerts(sb: SupabaseClient, accountIds: string[]): Promise<Map<string, Alert[]>> {
  const out = new Map<string, Alert[]>();
  if (accountIds.length === 0) return out;
  const since = new Date(Date.now() - WINDOW_H * 3600_000).toISOString();
  const [events, gold] = await Promise.all([
    sb.from("events").select("account_id, type, received_at, data").in("account_id", accountIds)
      .in("type", Object.keys(EVENT_TEXT)).gte("received_at", since)
      .order("received_at", { ascending: false }).limit(50),
    sb.from("metric_hourly").select("account_id, hour, value").in("account_id", accountIds)
      .eq("metric", "gold_net").gte("hour", since),
  ]);
  const push = (a: Alert) => out.set(a.account_id, [...(out.get(a.account_id) ?? []), a]);
  const seen = new Set<string>();
  for (const e of events.data ?? []) {
    const key = `${e.account_id}:${e.type}`;
    if (seen.has(key)) continue; // o mais recente de cada tipo
    seen.add(key);
    const { level, text } = EVENT_TEXT[e.type as string]((e.data ?? {}) as Record<string, unknown>);
    push({ account_id: e.account_id as string, level, text, at: e.received_at as string });
  }
  // ouro líquido da última hora fechada (o metric_hourly é refeito a cada 10 min; a hora corrente é parcial)
  const lastHour = new Date(Math.floor(Date.now() / 3600_000) * 3600_000 - 3600_000).getTime();
  const byAccount = new Map<string, number>();
  for (const r of gold.data ?? []) {
    if (new Date(r.hour as string).getTime() !== lastHour) continue;
    byAccount.set(r.account_id as string, (byAccount.get(r.account_id as string) ?? 0) + Number(r.value));
  }
  for (const [id, v] of byAccount) {
    if (v < -50_000) {
      push({
        account_id: id, level: v < -500_000 ? "critical" : "warning",
        text: `Perdendo ouro: ${Math.round(v / 1000).toLocaleString("pt-BR")} mil na última hora`,
        at: new Date(lastHour).toISOString(),
      });
    }
  }
  for (const list of out.values()) list.sort((a, b) => (a.level === b.level ? 0 : a.level === "critical" ? -1 : 1));
  return out;
}
