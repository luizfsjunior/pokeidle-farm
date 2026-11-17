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

## O que descobrimos (17/11, wiki do jogo e vendas reais)

Fontes: `pokepedia.mjs` (a wiki do jogo, em `game_files`), `outlandTiers` das regras do servidor e
`market_reference(14)` (mediana das vendas reais, 14 dias).

**Tiers da Outland.** São 40, e o tier liberado depende do **nível do treinador**: Outland 1 no 150 (×1),
Outland 2 no 500 (×1,1), Outland 4 no 1.000 (×1,25), Outland 9 no 2.250 (×2), até Outland 40 no 65.000 (×20). É o
**mesmo mapa, os mesmos pokémon e o mesmo nível 150** em todos: o tier só multiplica os cinco drops raros (Boss Token,
fragmentos de Key, Shiny Stone e Bicycle, Osso do Sacrifício), depois do Loot Boost. XP, ouro, captura e pedras não
mudam. Não há o que escolher: vale o maior tier liberado.

**Chances na Outland 1** (padrão da wiki): cada fragmento **1 em 250 mil** abates; Bronze Boss Token **1 em 10 mil**;
Osso do Sacrifício: chance em `shared/sacrificio.mjs`, que ainda não baixamos. Na Outland **não rola shiny**, e as
variantes de lá (#2001 a #2058) não evoluem.

**Para que servem e quanto vendem** (mediana, gemas):

| Item | Mediana | Vendas 14 d | De onde vem | Uso no jogo |
|---|---|---|---|---|
| Key Fragment | 220 | 274 | Outland | 10 viram uma casa de raridade sorteada (Professor Carvalho) |
| Bicycle Fragment | 160 | 173 | Outland | 10 viram uma bicicleta |
| Shiny Stone Fragment | 86 | 318 | Outland | 10 viram uma Shiny Stone do tipo escolhido (evolui shiny); a pedra pronta **não** é negociável |
| Bronze Boss Token | 3 | 1.387 | Outland | entrada de boss e do Raid semanal |
| Sacrifice Bone | 55 | 14 | Outland | pontos na barra do Sacrifício |
| Mega Stone Fragment | 84 | 96 | bosses (a região com Megas no dia) | Mega Evolução |
| Mega Shiny Stone Fragment | 350 | 108 | bosses | Mega Evolução shiny |
| Safari Ticket | 306 | 6 | bosses | Safari |
| Shiny Egg Fragment | 1.500 | 8 | hunts de **Unova** para frente (nível 5.000) | Ovo Shiny |

**Conta.** Na Outland 1, a ~1.000 abates/h: fragmentos (220 + 160 + 86) × 1/250 mil + token 3 × 1/10 mil ≈ 0,0022
gema por abate, menos 15% ≈ **~2 gemas/h por conta (~US$ 0,40 por dia)**. Os tiers só dobram isso no nível 2.250.
A Outland **não é uma mina** por si: o valor dela está mais no **Boss Token**, a porta para os bosses, que soltam os
fragmentos de Mega (84 e 350), as peças de TM e os tickets (Safari a 306).

## Próximos a investigar

- **Bosses** (`shared/bosses-lendarios.mjs`, ainda não baixado): nível mínimo por par, chance de fragmento de Mega por
  luta, quantos tokens custa cada luta. Se uma luta rende ~1 fragmento de Mega Shiny (350) por poucos tokens (3 cada),
  esse é o caminho de renda, e a Outland vira só a fábrica de tokens.
- Osso do Sacrifício: chance e o que a barra do Sacrifício dá.
- As chances reais vêm do welcome (`c.d.casas.fragmento.chanceDrop` etc.); a wiki mostra o padrão. Conferir no welcome.
- Loot Boost (Loja): quanto multiplica e quanto custa.
