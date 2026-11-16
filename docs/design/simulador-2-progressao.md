# Simulador, camada 2: progressão até o nível 150

Status: **rascunho** (16/11/2026). Decisões P-A a P-E em aberto (fim do documento). Base: a camada 1
([simulador-1-combate.md](simulador-1-combate.md)), validada e já usada pelo foco XP.

## Objetivo

Dado o estado de uma conta (nível e XP do treinador, time, bolsa, ouro), simular nível a nível até o **treinador 150**
e devolver o **plano**: em cada faixa de nível, qual hunt, qual ativo, quando evoluir, quanto ouro e poção custa, e o
**tempo total**. É o que o worker segue em contas novas e o que o agente consulta ("e se eu fizer X?").

## Regras do jogo usadas

- XP do treinador e do pokémon seguem a mesma curva, `total_xp(L) = 50/3·(L³ − 6L² + 17L − 12)` (conferido: o
  Bulbasaur 24 da conta tem `xpNivel` 179.400 = total_xp(24)). Cada abate dá a mesma XP aos dois; por isso o inicial anda
  colado no treinador.
- XP por abate = ⌊0,6·n²⌋ + 8 (n = nível da hunt) × o bônus da conta (medido: **2,1×**, ver P-C).
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

Somando os tempos, sai o tempo até o 150. O plano marca as trocas de hunt e as evoluções.

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

- `worker/src/pokeidle_farm/model/progression.py` (puro): `plan_to(level_goal, account) -> Plan` com as fases (faixa de
  nível, hunt, ativo, XP/h, horas, poções, ouro) e o tempo total.
- O foco XP grava o plano junto do `gems.plan` (ETA até o 150) e o painel mostra o ETA na conta.
- Testes com espécies e hunts de mentira (como os da camada 1) e a validação contra a conta.

## Decisões em aberto

- **P-A. Sobrevivência e economia**: modelar o dano do selvagem, as poções (ouro) e o ouro por abate, e descartar as
  hunts em que o ouro não se paga (proposta), ou deixar isso só medido?
- **P-B. Evolução automática**: o worker evolui sozinho quando o nível chega e a pedra está na bolsa (proposta; preciso
  descobrir a mensagem do botão "Evoluir" e protegê-la nas 5 pedras guardadas pelo seller)?
- **P-C. Bônus de XP de 2,1×**: de onde vem (VIP, evento, boost)? Se for temporário, o plano usa 1× quando acabar.
- **P-D. Escopo**: a camada 2 trata só o inicial e as evoluções dele (proposta); capturar e treinar um segundo pokémon
  fica para a camada 3 (sorte da captura) e a 4 (decisões).
- **P-E. Onde mostrar**: ETA e plano no card da conta no painel (proposta) ou só no evento?
