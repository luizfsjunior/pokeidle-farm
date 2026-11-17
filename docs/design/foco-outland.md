# Foco Outland (planejado)

Status: **em estudo** (17/11/2026). O caminho de renda mais provável são os bosses a partir de Johto (nível 650); a Outland é a fonte (fraca) de tokens.

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

## Bosses (17/11, `shared/bosses-lendarios.mjs`, `safari.mjs`, `mistico.mjs`, `raid.mjs`)

**Regras.** Cada luta custa **1 Bronze Boss Token**, ganhando ou perdendo. Há 3 bosses por região (Kanto: Articuno,
Moltres, Zapdos), os três abertos todo dia. O prêmio gira entre eles às 18h de Brasília: um dá **TM**, outro **Mega**,
outro **tickets**; dá para lutar sempre no boss do prêmio que se quer. O treinador precisa do nível da região, e o boss
luta **sempre nesse nível**. Equipe ideal: **5 pokémon com pelo menos o nível do boss**; para cada um que falta, o dano
tomado ×3 (`3 ^ déficit`). O Loot Boost não vale. Há repetição automática enquanto houver token.

**Nível do boss** (`nivelMinimoDoPar`, par = região a partir de 0): Kanto **300**, Johto **650**, Hoenn **3.100**,
Sinnoh **9.750**, Unova 22.700 (`300 + 350·par³` a partir de Hoenn).

**Chance por vitória** (p = par + 1; cada vitória sorteia os dois itens do prêmio do dia):

| Prêmio do dia | Itens (mediana, gemas) | Chance de cada | Valor por vitória, líquido |
|---|---|---|---|
| Mega | Mega Stone Fragment (84) e Mega Shiny Stone Fragment (350) | 0,65% · p e 0,5% · p | **~1,95 · p** |
| TM | TM Disk Piece (107) e AoE TM Disk Piece (266) | 0,5% · p cada | ~1,59 · p |
| Tickets | Safari Ticket (306) e Mystic Ticket (sem vendas) | 0,25% · p e 0,0005% · p | ~0,65 · p |

**Conta por luta no boss de Mega**, com o token comprado a 3 gemas (1.387 vendas em 14 dias, sobra no Mercado):

| Região | Nível | Valor líquido por vitória | Saldo por luta ganha |
|---|---|---|---|
| Kanto | 300 | ~1,95 | **−1,05** (perde) |
| Johto | 650 | ~3,9 | **+0,9** |
| Hoenn | 3.100 | ~5,9 | +2,9 |
| Sinnoh | 9.750 | ~7,8 | +4,8 |

Sem contar as poções nem as derrotas (o token vai embora). Farmar o token na Outland não muda a conta: a ~1.000
abates/h sai ~0,1 token por hora, e vender o token rende 2,55 líquidas, então usar o próprio token custa o mesmo.

**Conclusão.** O caminho de renda é **boss a partir de Johto**: treinador no 650 e **5 pokémon no 650**, comprando
tokens a 3 e lutando no boss de Mega do dia. O lucro depende de quantas lutas cabem por hora e da taxa de vitória,
que só dá para medir lutando. Liquidez: ~8 Mega Shiny e ~7 Mega por dia no Mercado, o que segura poucas contas.

**Sacrifício** (`sacrificio.mjs`): sacrificar pokémon com nota ≥ 3,5 (fora o ativo, a equipe e lendários) dá pontos;
50 a 1.000 pontos viram um boost de **XP ×1,2** por 8 h a 14 dias. O Osso do Sacrifício (1 em 250 mil na Outland)
vale 100 pontos. É um acelerador para o foco XP, não renda.

## Próximos a investigar

- **Uma luta de verdade**: duração, taxa de vitória e poções gastas, com uma conta no nível do boss de Kanto (300).
  Mesmo perdendo dinheiro em Kanto, dá a medida de lutas por hora.
- Montar a equipe de 5 no nível do boss: hoje o foco XP só sobe o ativo. Ver o XP Share e o que divide XP com a equipe.
- O Sacrifício como boost do foco XP: quantos pokémon de nota ≥ 3,5 as contas capturam por dia.
