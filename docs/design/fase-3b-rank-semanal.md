# Fase 3b — foco "rank semanal" (rascunho)

Status: **rascunho**, 13/11/2026. Tem decisões em aberto (seção 7) e coisas a confirmar no jogo (seção 6)
antes de implementar.

## 1. Objetivo

Um terceiro foco por conta, além de **captura** e **ouro-xp-drop** (fase 3a): subir no ranking semanal de
capturas capturando **um de cada espécie** e passando para a próxima. O worker escolhe a hunt, joga bola só
nos selvagens que ainda contam para a semana e troca de hunt quando a atual não tem mais o que render.

## 2. O que já sabemos

- **`topCatchNova`** chega no mesmo frame do `bola` com `sucesso: true`, com `sp`, `chave`, `n`, `m`, `s` e
  `pontua`. Parece ser a entrada no ranking da semana; `pontua` sugere que nem toda captura pontua
  (provavelmente só a primeira de cada espécie na semana). Hoje é gravado como `battle.topCatchNova`, sem `data`.
- **`welcome.hunts[]`**: ~1.000 hunts com `area`, `nivel`, `especies[]` e `totalSpawns`. É o catálogo para
  planejar. O `welcome` inteiro fica no `raw` do `state.snapshot` a cada conexão.
- **`estado.dexMud`**: capturas (`c`) e abates (`k`) por espécie, mas de sempre, não da semana.
- **`hunt.select {slug}`** troca de hunt, só fora da trava de combate (`estado.centroLivreEm`; cada golpe
  recebido renova a trava). Ainda não confirmado no DevTools.
- **`ball.throw {ballId, slot}`** joga uma bola num selvagem abatido: janela de ~30 s, ~1,3 s entre
  arremessos. Ainda não confirmado. É o que permite jogar bola **só** nas espécies que faltam, em vez da bola
  automática, que joga em todo selvagem.
- Captura: `captura` do `welcome` (`base`, `piso`, `teto`, `porDegrau`) e `catchRate` das bolas (×1 a ×4).
  Em Magikarp, Poké Ball ≈ 0,3% e Ultra Ball ≈ 1,2% por arremesso.
- Bola automática exige VIP; `ball.throw` manual provavelmente não (a confirmar).

## 3. Como funcionaria

### 3.1 Estado da semana

- **Espécies que já pontuaram na semana**: dos `topCatchNova` com `pontua: true` desde o início da semana
  (data de virada a confirmar). Na subida do plugin, lê os eventos da semana em `events` (como o teto do
  `restock` faz). Se o jogo mandar a lista da semana no `welcome`, usa ela e dispensa o histórico.
- **Faltam**: espécies que aparecem em hunts alcançáveis e ainda não pontuaram.

### 3.2 Escolha da hunt

Para cada hunt alcançável (nível e área liberados para a conta, seção 6), estima as **espécies novas por hora**:

```
novas/h(H) = Σ sobre espécies s que faltam em H:  abates/h × P(spawn de s em H) × P(captura de s com a bola)
```

- `abates/h`: medido na própria hunt quando há dados; senão, a média da conta em hunts de nível parecido.
- `P(spawn)`: pelo peso da espécie em `especies[]` (ou uniforme, se não houver peso).
- `P(captura)`: pela tabela `captura` e o `catchRate` da bola.
- Na prática é uma soma que encolhe: cada espécie capturada sai da conta. Hunt com 3 espécies faltando rende
  mais que uma com 1, mesmo que mais lenta.

Fica na hunt enquanto ela rende pelo menos `switch_ratio` (ex.: 70%) da melhor alternativa, com permanência
mínima de `min_dwell_min` (ex.: 15 min) para não ficar pulando. Quando não sobra espécie nova em lugar nenhum
alcançável, cai para o foco `fallback` (ex.: captura ou ouro-xp-drop).

### 3.3 Bolas

**Primeiro candidato: o `autoBallAteCapturar` do próprio jogo.** Pelo nome, joga bola numa espécie até
capturá-la e depois para de jogar nela. Se for isso, resolve a 3b sem `ball.throw`: o jogo faz a escolha no
servidor, com menos ações nossas. Falta saber (seção 6, item 4) se "já capturada" é pela semana ou pela dex
de sempre, se ele joga em todo selvagem até a primeira captura da hunt, e se continua depois de trocar de hunt.
Se não servir, o plano B é o `ball.throw` manual abaixo.

Plano B:

- **Bola automática desligada** (`auto.set` com `autoBallSemParar` e `autoBallAteCapturar` em `false`).
- O plugin escuta `kill` e, se a espécie falta e o slot ainda está na janela, manda `ball.throw` com a
  melhor bola em estoque. Depois de cada `fugiu`, joga de novo se ainda houver janela.
- Para numa captura com `pontua: true` daquela espécie.
- Sem prejuízo de ouro aqui não faz sentido (uma espécie nova vale muito mais que o ouro do abate), então o
  limite é um **orçamento semanal de bolas** em ouro (`weekly_ball_budget`).

### 3.4 Quem manda em quê

O `auto.set` e as compras não podem ter dois donos. Proposta:

- O `restock` ganha o foco `rank`: **não** escolhe a bola nem mexe nas flags de bola; só mantém estoque da
  bola definida em `rank_ball` (padrão Ultra Ball) e das poções.
- Um plugin novo, **`rank`**, é dono da escolha de hunt (`hunt.select`) e dos `ball.throw`.
- Só sobe se o foco da conta for `rank`; com outro foco ele fica parado.

## 4. Ações novas

| Ação | Intervalo mínimo | Observação |
|---|---|---|
| `HuntSelect(slug)` | 5 min | fila até a trava de combate acabar; confirmação pelo `huntSlug` no `estado` |
| `BallThrow(ballId, slot)` | 1,3 s | só em `kill` de espécie que falta, dentro da janela de 30 s |

As duas passam pelo `ActionGateway` (modo, rate limiter, `action.sent`). Teto de `hunt.select` por hora
(ex.: 6) para não parecer abuso e não sobrecarregar.

## 5. Métricas e painel

- Base nova: `rank_points` (capturas com `pontua: true`) e `rank_species_week` (espécies distintas na semana).
- Evento `rank.plan` a cada decisão de hunt: hunt atual, candidatas com `novas/h`, o que falta. No painel,
  um card "Rank semanal" com espécies na semana, posição (se o jogo informar) e a hunt atual.
- Um objetivo do tipo `metric` em `rank_species_week` já funciona com o que existe.

## 6. A confirmar no jogo (DevTools, pela conta pessoal)

1. **Como funciona o ranking**: o que pontua (espécie distinta? só a primeira captura de cada?), quando vira
   a semana (dia e hora), se tem prêmio, onde aparece a posição. Prints da tela do ranking ajudam.
2. **`topCatchNova`**: o que são `n`, `m`, `s` e `chave`. Comparar com a tela do ranking logo depois de uma
   captura.
3. **`hunt.select`**: trocar de hunt na mão e anotar a mensagem enviada e o que volta (`estado.huntSlug`?
   um `campo` novo?). Tentar durante a trava de combate para ver o erro.
4. **`autoBallAteCapturar`** (antes do `ball.throw`): ligar só ele, numa hunt com uma espécie já capturada
   e outra nunca capturada. Ver em quais selvagens sai `bola`, se para depois da captura e se volta a jogar
   numa espécie capturada em outra semana. Se não servir: com a bola automática desligada, jogar uma bola na
   mão e anotar a mensagem do `ball.throw` e o `slot`.
5. **Hunts alcançáveis**: o que limita (nível da conta, área desbloqueada, viagem)? Dá para ir direto de uma
   hunt para outra de outra área?
6. **Catálogo**: rodar no SQL Editor e me mandar o resultado (não tem token nem dado da conta):
   ```sql
   select jsonb_pretty(raw->'hunts'->0) as exemplo, jsonb_array_length(raw->'hunts') as total,
          jsonb_pretty(raw->'captura') as captura
     from public.events where type = 'state.snapshot' order by received_at desc limit 1;
   ```

## 7. Decisões em aberto

- Quais contas ficam no foco `rank` (uma, todas, revezando)?
- Orçamento semanal de bolas (`weekly_ball_budget`) e a bola do rank (`rank_ball`).
- Foco de volta quando acabarem as espécies alcançáveis (`fallback`).
- Se vale capturar espécies que só aparecem em hunts acima do nível da conta subindo de nível antes
  (fica fora da 3b; seria um plano de várias semanas).

## 8. Ordem de implementação

1. Confirmar a seção 6 e fechar a seção 7.
2. Tradutor: `topCatchNova` com `data` (`species`, `pontua`, ...) e `hunt.changed` confiável.
3. Catálogo de hunts a partir do `welcome` + estimador de `novas/h`, com testes.
4. Plugin `rank` em `observe_only`: grava `rank.plan` e as ações que faria. Conferir por alguns dias.
5. `ball.throw` ligado, depois `hunt.select`.
6. Métricas e card no painel.
