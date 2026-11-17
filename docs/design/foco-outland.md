# Foco Outland (planejado)

Status: **planejado** (17/11/2026). Começar quando a primeira conta chegar no nível 150.

## Por quê

Antes do 150 não há gema de verdade: as pedras vendem a 2 gemas com filas de semanas, e o foco por pedras saiu do
painel (17/11). O dinheiro começa na Outland, onde caem os fragmentos (Key, Shiny Stone, Bicycle) e o Bronze Boss
Token, que vendem de verdade. Até lá, todas as contas ficam no **foco XP**, que é o que leva ao 150 mais rápido.

## Ideia

Um quarto objetivo do plugin `gems` (`objective: "outland"`), ao lado de `xp`:

- **Hunt:** a da Outland com mais gemas por hora, pela mesma conta do card Outland
  ([outland-potencial.md](outland-potencial.md)): abates/h × Σ (chance × mult. do tier × mediana das vendas reais × 0,85).
  Com o ritmo medido substituindo a previsão do simulador assim que a conta farmar lá.
- **Tier:** se a conta puder escolher o tier da Outland, pesar o multiplicador de drop contra a queda de abates/h.
- **Venda:** o `seller` passa a vender fragmentos e tokens com a mesma regra de liquidez das pedras (fila e vendas por
  dia), guardando o que for preciso para trocas do próprio jogo.
- **Painel:** opção "Outland" no card Foco, só para conta com nível ≥ 150.

## A descobrir antes de fazer

- O formato de `outlandTiers` e se o tier muda o nível e o HP do selvagem.
- Os nomes exatos dos itens no Mercado (o card Outland mostra "sem venda" quando não casa).
- Se os fragmentos têm uso no jogo (montar a Key, a Bicycle) que valha mais do que vender.
- Shiny: não há nas hunts da Outland; capturar para vender pokémon é outro caminho (o worker hoje só vende itens).
