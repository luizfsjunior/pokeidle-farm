/** Nome e para que serve cada plugin (a aba Ajustes mostrava só o nome técnico; refatoracao-2026-11-20, 4.3).
 *
 * A aba Ajustes mostra um card para cada plugin daqui, tenha ou não config gravada no banco (antes só apareciam os
 * que tinham linha em plugin_configs, e um plugin novo pedia "Adicionar plugin" com o nome digitado).
 *
 * `alwaysOn`: o worker sobe o plugin mesmo sem config e ignora o ligado/desligado (`always_on` no Python). Com
 * `activeKey`, o interruptor do card liga e desliga pelo `active` da config; sem ele, o card só mostra "sempre ligado".
 * A telemetria, o perfil e a vigia ficam de fora: são do worker, não têm o que ajustar. */
export type PluginInfo = { label: string; hint: string; managed?: string; alwaysOn?: boolean; activeKey?: boolean };

export const PLUGIN_INFO: Record<string, PluginInfo> = {
  restock: { label: "Reposição", hint: "Compra poções, revives e bolas abaixo do mínimo.", managed: "Modo (aba Agora)" },
  gems: { label: "Plano de hunt (XP/gemas)", hint: "Escolhe a hunt no modo XP.", managed: "Modo (aba Agora)" },
  rank: { label: "Rank semanal", hint: "Fila de espécies do rank, lançando até capturar.", managed: "Modo (aba Agora)" },
  team_train: { label: "Treinar a equipe", hint: "Sobe cada membro até o nível alvo.", managed: "Modo XP (aba Agora)" },
  hunt_hold: { label: "Hunt manual", hint: "Segura a hunt escolhida no painel até o prazo.", managed: "Desvio (aba Agora)" },
  capture_target: { label: "Capturar espécie", hint: "Vai para a hunt da espécie e lança até capturar.", managed: "Pokédex" },
  seller: { label: "Venda no Mercado", hint: "Anuncia as pedras e itens que sobram." },
  daily: { label: "Prêmios diários", hint: "Resgata o passe e os prêmios do dia." },
  evolve: { label: "Evolução automática", hint: "Evolui o ativo quando tem a pedra.", alwaysOn: true, activeKey: true },
  outland_tier: {
    label: "Tier da Outland", hint: "Sobe para o maior tier da Outland que o nível libera.", alwaysOn: true, activeKey: true,
  },
  ball_thrower: { label: "Lançador de bolas", hint: "Joga bola em todo shiny e na captura ativa.", alwaysOn: true },
  market_prices: { label: "Preços do Mercado", hint: "Lê as médias e os anúncios do Mercado de hora em hora.", alwaysOn: true },
};

export type PluginRow = { plugin: string; enabled: boolean; config: Record<string, unknown> };

/** Os plugins da conta para a aba Ajustes: os conhecidos na ordem de cima (com o padrão do worker quando não há
 * config gravada) e depois qualquer outro que tenha linha no banco. */
export function pluginRows(saved: { plugin: string; enabled: boolean; config: Record<string, unknown> | null }[]): PluginRow[] {
  const byName = new Map(saved.map((p) => [p.plugin, p]));
  const known = Object.entries(PLUGIN_INFO).map(([plugin, info]) => {
    const row = byName.get(plugin);
    return { plugin, enabled: row?.enabled ?? !!info.alwaysOn, config: row?.config ?? {} };
  });
  const extra = saved
    .filter((p) => !(p.plugin in PLUGIN_INFO))
    .map((p) => ({ plugin: p.plugin, enabled: p.enabled, config: p.config ?? {} }));
  return [...known, ...extra];
}
