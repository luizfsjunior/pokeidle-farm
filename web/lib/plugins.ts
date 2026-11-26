/** Nome e para que serve cada plugin (a aba Ajustes mostrava só o nome técnico; refatoracao-2026-11-20, 4.3). */
export const PLUGIN_INFO: Record<string, { label: string; hint: string; managed?: string }> = {
  restock: { label: "Reposição", hint: "Compra poções, revives e bolas abaixo do mínimo.", managed: "Modo (aba Agora)" },
  gems: { label: "Plano de hunt (XP/gemas)", hint: "Escolhe a hunt no modo XP.", managed: "Modo (aba Agora)" },
  rank: { label: "Rank semanal", hint: "Fila de espécies do rank, lançando até capturar.", managed: "Modo (aba Agora)" },
  team_train: { label: "Treinar a equipe", hint: "Sobe cada membro até o nível alvo.", managed: "Modo XP (aba Agora)" },
  hunt_hold: { label: "Hunt manual", hint: "Segura a hunt escolhida no painel até o prazo.", managed: "Desvio (aba Agora)" },
  capture_target: { label: "Capturar espécie", hint: "Vai para a hunt da espécie e lança até capturar.", managed: "Pokédex" },
  seller: { label: "Venda no Mercado", hint: "Anuncia as pedras e itens que sobram." },
  market_prices: { label: "Preços do Mercado", hint: "Lê as médias e os anúncios do Mercado de hora em hora." },
  daily: { label: "Prêmios diários", hint: "Resgata o passe e os prêmios do dia." },
  evolve: { label: "Evolução automática", hint: "Evolui o ativo quando tem a pedra." },
  outland_tier: { label: "Tier da Outland", hint: "Sobe para o maior tier da Outland que o nível libera." },
};
