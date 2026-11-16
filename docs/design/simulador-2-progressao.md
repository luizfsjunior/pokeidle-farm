# Simulador, camada 2: progressão até o nível 150

Status: **implementado** (16/11/2026), decisões P-A a P-E tomadas (fim do documento). Base: a camada 1
([simulador-1-combate.md](simulador-1-combate.md)), validada e já usada pelo foco XP.

## Objetivo

Dado o estado de uma conta (nível e XP do treinador, time, bolsa, ouro), simular nível a nível até o **treinador 150**
e devolver o **plano**: em cada faixa de nível, qual hunt, qual ativo, quando evoluir, quanto ouro e poção custa, e o
**tempo total**. É o que o worker segue em contas novas e o que o agente consulta ("e se eu fizer X?").

## Regras do jogo usadas

- XP do treinador e do pokémon seguem a mesma curva, `total_xp(L) = 50/3·(L³ − 6L² + 17L − 12)` (conferido: o
  Bulbasaur 24 da conta tem `xpNivel` 179.400 = total_xp(24)). Cada abate dá a mesma XP aos dois; por isso o inicial anda
  colado no treinador.
- XP por abate = ⌊0,6·n²⌋ + 8 (n = nível da hunt) × os bônus da conta, que vêm em `estado.bonusXp.partes` com a
  expiração (`ate`): em 16/11, VIP 1,5× até 12/12 e evento 1,4× até 16/11 08:22 UTC (juntos, os 2,1× medidos).
- Ouro por abate = 36 × nível^0,6007 × (1 + 15% de bônus de loot × (1 + farm do evento)) (`sell-value.mjs`); na Kabuto
  dá ~250, e o ouro líquido previsto (82 mil/h) bateu com o medido (~88 mil/h).
- Poções: a Small Potion cura 60 HP por 50 de ouro (a que o restock compra). O dano que o ativo sofre vem da camada 1:
  o selvagem bate com os golpes dele × `multDanoSelvagem` (1,8), no máximo a cada 1,4 s, enquanto a luta dura.
  Previsto × medido: Horsea 90 × ~60 poções/h, Kabuto 502 × ~740.
- Hunts liberadas: nível da hunt ≤ nível do treinador. Kanto tem hunts nos níveis 1, 10, 20 … 80 e 100; a Outland abre
  no 150.
- Evolução: nível exigido + 1 pedra do tipo (Bulbasaur → Ivysaur no 40, → Venusaur no 80, Leaf Stone). Ao evoluir, os
  stats base e os golpes mudam (Venusaur ganha Petal Blizzard, poder 160, no 26).
- Um pokémon só luta até 5 níveis acima do treinador (o inicial é exceção).

## O modelo

Para cada nível L do treinador, de agora até o 150:

```
melhor hunt(L) = argmax sobre hunts ≤ L de abates/h(ativo em L, hunt) × XP por abate(hunt)   [camada 1]
tempo(L → L+1) = (total_xp(L+1) − total_xp(L)) ÷ XP/h da melhor hunt
```

Somando os tempos, sai o tempo até o 150. O plano marca as trocas de hunt e as evoluções. Detalhes:

- só entram hunts que se pagam em ouro (ouro dos abates − poções ≥ 0); sem nenhuma, o plano para (`stuck_at`);
- folga de 15% como o foco XP: fica na hunt da fase anterior se a melhor não render 15% a mais;
- desempenho: a cada nível só são simulados os 3 níveis de hunt mais altos liberados e as 8 melhores do nível anterior
  (no primeiro, todas); ~30 s por plano até o 150, numa thread.

## Protótipo (16/11, Bulbasaur da conta: IV 27, qualidade 1,6, P2, bônus 2,1×)

| | sem evolução | com evolução (Ivysaur 40, Venusaur 80) |
|---|---:|---:|
| do 26 ao 150 | **26 h** | **21 h** |

Caminho com evolução: Kabuto (até o 39) → Graveler (40–59) → Onix (60–109) → Kabutops (110–149); XP/h sobe de ~240
mil para ~4,7 milhões. Para uma conta nova, do nível 5 ao 150: **Bulbasaur 23,8 h**, Squirtle 30,3 h, Charmander 32,3 h
(o Bulbasaur leva vantagem porque Pedra/Água/Terra dominam as hunts boas de Kanto).

**O que o protótipo ainda não tem** (por isso é otimista): o dano do selvagem (×1,8 a cada 1,4 s), o gasto de poções e
ouro, as idas ao Centro e as trocas de hunt (a trava e os 20 s). Na Kabuto o jogo mostrou ~740 poções/h; em hunts
mais altas o selvagem bate mais.

## Validação

1. **Curto prazo**: o plano prevê o tempo de cada nível. A conta de teste está no 27; comparar o tempo previsto com o
   real nível a nível (critério: erro mediano ≤ 25%, como na camada 1).
2. **Economia**: poções/h e ouro/h previstos contra os medidos (Horsea ~60 poções/h e ~140 mil de ouro/h; Kabuto ~740 e
   ~88 mil).

## Entregas

- `worker/src/pokeidle_farm/model/progression.py` (puro): `plan_to(goal, account, hunts, raw_species, rules, now)` →
  `Plan` com as fases (faixa de nível, hunt, ativo, horas, abates/h, XP/h, poções/h, ouro líquido/h), as evoluções e
  o tempo total; `combat.simulate_hunt` devolve abates/h e dano sofrido/h.
- `worker/src/pokeidle_farm/progress.py`: `Progress`, usado pelo plugin gems no foco XP. Grava `progress.plan` na
  subida, a cada nível, ao evoluir e no máximo a cada `plan_every_min` (60); e manda `pokemon.evoluir`
  (`{pokemonId, alvoId}`) quando o ativo chega no nível e a pedra do tipo (o `type1`) está na bolsa (uma tentativa
  por pokémon e espécie a cada 10 min; o servidor valida e gasta a pedra). `GemsConfig`: `plan_goal` (150),
  `plan_every_min`, `auto_evolve` (ligado).
- O tradutor guarda a XP do treinador, o `bonusXp` e o `evento` do `estado`; a sessão copia para o `AccountStateView`.
- Painel: o card Foco XP mostra "Até o nível 150" (horas, previsão de chegada, evoluções e as fases).
- Testes: `test_progression.py` (espécies e hunts de mentira) e `test_protocol.py` (o que o tradutor guarda).

## Plano da conta de teste (16/11, treinador 27)

~26 h até o 150: Kabuto (27–39) → Rhyhorn (39–41; evolui para Ivysaur no 40) → Graveler (41–60) → Onix (60–114;
Venusaur no 80) → Kabutops (114–150). A partir do 100 o selvagem bate forte: 750 a 5.000 poções/h, e o ouro líquido
cai para perto de zero na Kabutops; poções maiores (Ultimate: 3.000 HP por 1.500, 0,5 de ouro por HP contra 0,83 da
Small) passam a compensar quando o HP máximo cresce. Fica para depois (restock).

## Melhorias (16/11, depois da primeira versão)

- **Poção certa**: o restock (`potion_auto`, ligado) troca a poção das regras pela de menor ouro por HP útil para o
  HP máximo do ativo (a automação bebe abaixo de 30%, então cada poção cura no máximo 70% do HP): Small até ~1.400
  HP, Hyper até ~4.300, Ultimate até ~7.100, Golden (50% do HP) acima. Mínimo e alvo viram o mesmo HP de estoque.
  O plano usa a mesma escolha (`Phase.potion_id`).
- **Trocas de hunt**: +2 min por troca no plano (trava, pedido engolido, primeira onda).
- **Verificação da evolução**: depois de `progress.evolve`, o worker grava `progress.evolved` quando a espécie do
  ativo muda ou `progress.evolve_failed` se 2 min passam sem mudar. **Pendente**: conferir na conta de teste no nível
  40 (primeira evolução de verdade).
- **Atenção, teto do restock**: o `max_gold_per_hour` (50 mil) fica abaixo do gasto em poção previsto do nível ~60 em
  diante; com o teto, as poções acabam e o pokémon desmaia.

## Decisões (16/11)

- **P-A.** Modelar o dano do selvagem, as poções e o ouro; descartar as hunts que não se pagam.
- **P-B.** Evolução automática no foco XP.
- **P-C.** Os bônus são lidos do `estado.bonusXp` (VIP, evento...), cada um até expirar.
- **P-D.** Só o inicial e as evoluções dele; o segundo pokémon fica para as camadas 3 e 4.
- **P-E.** ETA e plano no card da conta.
