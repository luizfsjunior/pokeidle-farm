# Progressão e Mercado: onde está o dinheiro e como chegar lá (15/11/2026)

Continuação da [análise de 15/11](analise-2026-11-15.md). Fontes: código público do jogo (`app.js`, `pokepedia.mjs`,
`/shared/*.mjs`, v1.420.0), a varredura do Mercado feita pelo worker (histórico global de vendas e anúncios de
pokémon, 23:12 UTC) e os eventos gravados da `luizfsjunior_1` (treinador nível 21–23, Bulbasaur ativo).

## 1. Onde está o dinheiro

| Fonte | O que vimos | Para a conta hoje |
|---|---|---|
| Pedras de evolução | todas a **2 gemas** no menor anúncio, filas de centenas a 45 mil ([fase-9](design/fase-9-venda-de-pedras.md)) | bônus; ~1 gema líquida cada |
| Key / Shiny Stone / Bicycle Fragment | vendas reais a **~222 / ~89 / ~178 gemas**; Key Fragment vendeu 28 em 6 min | só na **Outland (nível 150)**, 1 em 250 mil abates cada na Outland 1; desde 16/11 são 40 degraus, até ×20 no nível 65.000 (era 1 em 200 mil e ×1,25 a ×8; ver [regras-do-jogo](regras-do-jogo.md#outland-desde-1611)) |
| Mega Shiny Stone Fragment | vendas reais a **~538 gemas** | origem ainda a ver |
| Bronze Boss Token | 1.446 vendidos em 6 min a **~3 gemas** | Outland, 1 em 10 mil abates na Outland 1 (0,01% hoje; aqui estava 0,05%), até 1 em 500 na Outland 40 |
| TM Disk Piece / AoE | médias de 161 / 290 gemas; uma AoE vendida a 247 | origem ainda a ver (bosses?) |
| **Pokémon shiny** | anunciados de **35 mil a 175 mil gemas** (US$ 300 a 1.500); Larvitar shiny nível 23 a 65 mil | shiny = 1 em 24.000 capturas; precisa de capturas em volume |
| Pokémon fortes não shiny | anúncios de 50 mil a 79 milhões são "não vendo"; P5/nota alta ainda sem dado | Mercado só aceita nível ≥ 50 e nota ≥ 3,5 (shiny, P5 e lendário em qualquer nível) |

**Conclusão:** o dinheiro está em **shiny** (capturas em volume) e nos **fragmentos da Outland** (nível 150 e, de
verdade, tiers altos). Os dois pedem progressão: subir de nível para alcançar a Outland e hunts mais fortes, e ter
pokémon fortes para capturar rápido. As pedras são bônus.

O histórico global trouxe só itens: o filtro `tipo: "pokemon"` não foi aceito como enviamos. Falta descobrir o formato
para ter **vendas reais** de pokémon (os números acima são anúncios).

## 2. Como o jogo funciona (o que importa para progredir)

Do capítulo de combate e de níveis da wiki do jogo:

- **Só o pokémon ativo luta.** Os outros do time entram se ele desmaiar.
- **Cada abate dá a mesma XP ao treinador e ao pokémon ativo.** O nível do treinador destrava áreas; o do pokémon
  aumenta os stats. Um pokémon só entra em campo até alguns níveis acima do treinador (o inicial é exceção).
- **XP por abate** = ⌊0,6 × nível do selvagem²⌋ + 8 (até 150; acima, 0,6 × 150² × (n/150)^1,25, como em
  `xp_model.py`: a hunt 200 paga ~19,3 mil, o que o guia "Todos os bônus de XP" confirma), multiplicada pelos bônus. Medido: ~1,65× a base
  (evento ×1,36 e VIP ×1,5 enquanto valiam).
- **XP para subir** de L para L+1 = 50·L² − 150·L + 200; total até L = 50/3·(L³ − 6L² + 17L − 12). Até o 30: 368 mil;
  até o 50: 1,85 milhão; até o 100: 15,7 milhões; **até o 150: 54 milhões**.
- **Dano** = ((2·nível/5 + 2) × poder × atk/def)/50 + 2, × 1,5 (golpe do próprio tipo) × efetividade de tipo. O selvagem
  tem HP ×5. Os stats crescem com o nível.
- **Multiplicadores de XP:** VIP +50%, XP Boost +50%, Boost dos Atrasados (×10 até o nível dos veteranos, 1.160 em
  17/11), guild, Sacrifício +20%, eventos. Eles se multiplicam.
- **Desmaiar o time inteiro custa 10% do XP do nível atual** do treinador (guia "O Mapa e o Hunt Analyser").

### Ritmo por nível do ativo

Como o dano cresce com o nível do ativo (fator (0,4·L + 2)·L, ~2× do nível 16 ao 23), o ritmo de uma hunt melhora
sozinho enquanto o pokémon sobe nela, até o teto (~1.100 abates/h: andar até o selvagem e ele reaparecer). As hunts
"lentas" (60–115/h) são as que mais melhoram. O worker passou a gravar o nível do ativo em cada abate e projeta o ritmo
medido para o nível atual ([design/ritmo-por-nivel.md](design/ritmo-por-nivel.md)).

### Onde a conta deveria estar agora

XP real por hora (média histórica, Bulbasaur 16–23):

| Hunt (nível) | Abates/h | XP/h | Ouro líquido/h |
|---|---|---|---|
| **Horsea (10)** | 608 | **68 mil** | **+74 mil** |
| Abra (10) | 318 | 36 mil | −4 mil |
| Charmander / Bulbasaur / Gastly (20) | 60–213 | 24–26 mil | negativo |
| Geodude (1), onde está | 1.134 | 19 mil | +44 mil |

Horsea (Água, fraco contra o Bulbasaur Grama) rende 3,5× a XP do Geodude e o maior ouro. **A vantagem de tipo do ativo
contra a hunt é o que mais pesa.**

### O time hoje

O Bulbasaur nível 23 (poder 68) é o único lutador; quatro Magikarps nível 1 (poder 1) ocupam o time. Zubat (12), Horsea
(9) e Abra (7), capturados nas hunts de nível 10, estão fora. Como só o ativo luta, o ganho está em **trocar o ativo
conforme a hunt** (`team.active`) e em capturar um segundo lutador de tipo complementar.

## 3. Protocolo para contas novas (até a Outland)

Estimativa: XP/h ≈ abates/h × (0,6·n² + 8) × bônus, numa hunt de nível n com vantagem de tipo. Se a conta fica em hunts
de nível ~L/2 com vantagem (~600 abates/h, como Horsea), XP/h ≈ 150·L², e subir um nível custa ~50·L²: **~0,35 h por
nível, ~50 h do 1 ao 150** (24 h/dia: ~2 dias). Sensibilidade: a 300 abates/h, ~100 h; no teto (~1.000/h), ~30 h. Os
bônus (VIP, XP Boost, Atrasados) dividem esse tempo.

| Fase | Níveis | Onde | Por quê |
|---|---|---|---|
| 1 | 1 → 10 | hunts de nível 1 com vantagem de tipo, no teto (~1.000 abates/h) | 9,3 mil XP: menos de 1 h |
| 2 | 10 → 30 | hunts de nível 10 com vantagem (ex.: Horsea para inicial Grama) | ~360 mil XP a ~65 mil/h: ~6 h |
| 3 | 30 → 150 | subir de faixa quando a hunt seguinte com vantagem render mais XP/h; trocar o ativo pelo tipo da hunt; capturar um segundo lutador de tipo complementar | o grosso: ~40 h |
| 4 | 150+ | Outland 1: fragmentos (Key, Shiny Stone, Bicycle) e Boss Token; shiny das capturas | onde o jogo "começa de verdade" |

Regras durante a subida:
- **Foco XP** (a construir): ficar na hunt de maior XP/h projetada (ritmo pelo nível do ativo × XP por abate), com
  histerese; bolas desligadas (ouro sobra para poções).
- Sem rank nem captura na subida; pedras guardadas (5 de cada) como bônus.
- Ativo trocado pela hunt quando houver alguém com vantagem (a construir: `team.active`).

## 4. Próximos passos

1. Deploy do ritmo por nível (já implementado, commit `a1b80aa`): começa a gravar o nível do ativo.
2. **Foco XP** no lugar do foco gemas para esta conta (o modelo do gems serve: troca o valor das pedras pela XP por
   abate).
3. **Equipar o ativo pela hunt** (`team.active`): escolher entre os pokémon da conta o de maior dano esperado contra o
   tipo da hunt.
4. Descobrir o filtro de pokémon no histórico global para ter vendas reais de shiny e de pokémon fortes, e varrer os
   shiny mais baratos (`ordem: "baratos"`) para saber o piso de um shiny comum.
