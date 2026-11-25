# Guias do pokeidleguide.io × worker: o que melhorar (25/11/2026)

Fonte: 17 dos 35 guias da comunidade em https://pokeidleguide.io/#guias (série do Liang e um guia do ALIZU,
atualizados entre 17 e 20/11 para o jogo 1.436 a 1.459), cruzados com o código do worker na `main` de 24/11
(`632c7d5`). As regras em si foram para [regras-do-jogo.md](regras-do-jogo.md#dos-guias-do-pokeidleguideio-25112026).

Lidos: bônus de XP, Mapa e Hunt Analyser, Tipos e combate, Captura, Entendendo o seu Pokémon, Conta segura, o site e
a extensão /hunt, As 40 Outlands, Prey e Bestiário, Dia Sazonal e Shield do Novato, Mercado (RMT), Top Catch e
Ranks, Gold, Sacrifício, Evolução e Oferenda, Bosses e Trocando seu inicial. Ficaram de fora PvP, Guild,
Campeonatos, lives, Diamantes e Passe, Gemas, Shiny, Ovos, Mega, Casas e Itens raros. As aulas 01 e 02, Rotas de
XP e Onde caçar são só vídeo.

## O que já está certo

O código lê as regras do próprio jogo e bate com os guias:

- XP por abate acima do 150 (`xp_model.py`): hunt 200 → 19.344 pelo modelo, 19.342 pelo guia.
- Ampliação de tipo na hunt (`model/combat.py`, ampliação 1,5): ×2 → ×2,5, ×4 → ×5,5, ×0,5 → ×0,33.
- Stats, sorteio de dano 0,85–1,00, Investida, recarga pelo IV de SPD, HP do selvagem ×5.
- Ouro por abate e bônus de loot de 15% (`model/progression.py`, `gold_per_kill`): nível 1 → 41, 100 → 658.
- Chances da Outland 1 (`outland_model.py`) e regras dos bosses ([design/foco-outland.md](design/foco-outland.md)).

## Melhorias, por prioridade

### P1: corrigir ou evitar perda silenciosa

**1. Shield do Novato no dia sazonal.** `season_factor` (`model/combat.py`) aplica o dia sazonal cheio dos dois
lados. Abaixo do nível dos veteranos (1.160 em 17/11; todas as nossas contas), o jogo protege o treinador: o
selvagem do tipo do dia não fica mais forte contra nós. Na hunt do tipo do dia, hoje o modelo erra assim:

| Situação | Modelo hoje | Jogo com Shield |
|---|---|---|
| nosso pokémon de outro tipo bate no selvagem do dia | ×¼ | ×1 |
| o selvagem do dia bate nele | ×2 | ×1 |
| nosso pokémon do tipo do dia bate no selvagem do dia | ×½ | ×2 |
| o selvagem do dia bate nele | ×½ | ×¼ |

Efeito: no dia sazonal, o foco XP foge sem motivo das hunts do tipo do dia, que para nós são neutras ou ótimas.
Correção: `Rules` ganha `novice_shield: bool` (nível do treinador abaixo do alvo do Atrasados; conferir se o
`dia-sazonal.mjs` ou o `estado` já mandam o alvo) e, com ele, o lado do selvagem ignora o ×2 do dia. Teste com a
tabela acima.

**2. Depot cheio trava a captura.** Com 3.000 pokémon no Depot, a bola não sai, nem a do `ball_thrower`, e nada
avisa. Hoje a venda do Depot (`shop.sellAllPokemons`) só existe como comando manual do painel
(`commands.py`, `_depot_sell`). Proposta, em dois passos:
- a vigia lê o tamanho do Depot no perfil e grava `watchdog.depot_high` a partir de ~2.700, com aviso no painel;
- depois, um plugin de limpeza: antes de vender, marca na Coleção (`colecao.mover`) o que vale guardar
  (shiny, P4+, lendário, Nota alta da espécie alvo) e manda o resto para venda ao NPC, Oferenda ou Sacrifício
  (itens 5 e 6). O jogo já pede uma segunda confirmação quando o lote leva pokémon especial (desde 19/11), então o
  plugin precisa tratar essa resposta, e não só o `Ack`.

**3. Risco de morte no foco XP.** Desmaiar o time inteiro custa 10% do XP do nível atual. A vigia já marca pares
(pokémon, hunt) perigosos depois de uma tempestade de revives, mas o ranking de hunts (`model/predict.py`,
`progression.py`) compara só XP/h e ouro/h. Acrescentar ao XP/h líquido: − mortes/h × 0,10 × XP do nível. As
mortes/h saem da telemetria (eventos de desmaio por hunt e pokémon) ou de um modelo de sobrevivência no
`simulate_hunt` (o selvagem bate ×1,8, golpe a cada 1,4 s, contra o HP e as poções do ativo). Perto de subir de
nível, uma morte custa muito, porque 10% do nível já é XP de várias horas.

### P2: ganhos baratos de estratégia

**4. Prey diário.** A roletada é grátis todo dia às 18:00 e dá, por um dia, Dano +10–50%, Spawn +1–5, Capture
Boost ou Defensivo contra uma espécie. O worker não usa. Plugin `prey`:
- depois das 18:00, faz a roletada grátis (nunca a paga) e lê as 9 espécies, o bônus e as estrelas;
- escolhe a espécie cuja hunt, alcançável e segura para o ativo, ganha mais XP/h com o bônus (Dano entra no
  `simulate_hunt` como multiplicador; Spawn como selvagens a mais por onda; Capture Boost só no foco de captura);
- o foco XP passa a considerar a hunt do Prey até as 18:00 do dia seguinte.

É preciso descobrir as mensagens do Prey no protocolo (o `app.js` tem a tela em Mochila → Prey). A extensão /hunt
do site faz essa mesma conta para validar.

**5. Sacrifício para XP.** Pokémon de Nota 3,5+ parados no Depot viram pontos; 1.000 pontos dão 14 dias de +20% de
XP, que multiplica com tudo. O código já tem a tabela (`model/capture.py`, `sacrifice_points`). Estratégia: em vez
de vender ao NPC os de Nota 3,5+, acumular até o nível 5 da barra (1.000 pontos) e resgatar quando a conta for
ficar dias no foco XP. Só resgatar no nível 5, porque o resgate paga só o maior nível e zera a barra. Nunca
sacrificar shiny, P4+ ou pokémon que o Mercado compra mais caro (Nota 3,5+ e nível 50+ já entra no Mercado:
comparar com o preço de referência antes).

**6. Oferenda no lugar da busca de pedra.** Hoje, sem a pedra para evoluir, o foco vira busca pela hunt que mais
dropa a pedra ([design/foco-xp-pedra.md](design/foco-xp-pedra.md)). Com 5 pokémon do tipo primário no Depot (Nota
abaixo de 3,5), a Oferenda dá a pedra garantida na hora, e ainda limpa o Depot. Ordem: Oferenda se houver 5 do
tipo; senão, Mercado se a pedra estiver barata; senão, a busca de hoje.

**7. Marcos do Top Catch.** 10 espécies na semana dão 30 min de XP Boost Trainer, 25 dão 30 min de XP Boost
Pokémon e 50 dão os dois por 1 h, somando ao que houver. Para uma conta no foco XP, capturar 10–25 espécies baratas
(hunts de nível baixo com Poke Ball, onde a captura é rápida) pode valer o desvio. Avaliar no simulador: tempo da
volta contra horas de boost. O plugin `rank` já sabe montar a fila de espécies e só precisa de uma meta por marco.

**8. Seletor da Outland.** O jogo não sobe a Outland sozinho quando o treinador sobe de nível. `outland_model.py`
já calcula o maior degrau liberado (`tier_mult_at`), mas não existe ação para trocar o degrau. Quando houver foco
Outland, ele precisa garantir o degrau mais alto liberado. Somar também o Osso do Sacrifício aos drops: chance igual
à dos fragmentos (1 em 250 mil na Outland 1), vendável e com valor de 100 pontos de Sacrifício.

### P3: depois

**9. Calibrar o simulador contra o /hunt do site.** O /hunt e a extensão usam as fórmulas do jogo e mostram
abates/h e risco por hunt para um pokémon colado. Comparar com `simulate_hunt` para 3 ou 4 pokémon das nossas
contas é um teste barato do modelo de ondas e de combate.

**10. Bestiário.** No máximo +0,5% por espécie. Só vale exibir no painel; não muda decisão.

**11. Treino da equipe para o boss.** Para levar 5 pokémon ao 300 ([design/team-train.md](design/team-train.md)),
a Casa (25% a 100% do XP do ativo para outro pokémon) e o Exp. Share (5%) treinam sem trocar o ativo. Exigem
comprar a Casa ou o item; avaliar preço no Mercado antes.

**12. Contas novas.** E-mail sem `+` e vínculo de contas permanente: colocar no checklist do
[deploy.md](deploy.md) antes de cadastrar a próxima conta de farm.

## Próximo passo sugerido

1 e 2 primeiro: o Shield é uma mudança pequena no modelo com teste direto, e o Depot é o risco de a conta caçar
dias sem capturar nada. Depois o Prey (4), que é o maior ganho diário sem gastar nada.
