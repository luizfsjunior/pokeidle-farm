# Fase 3b — foco "rank semanal" (rascunho)

Status: **rascunho**, 13/11/2026. Tem decisões em aberto (seção 7) e coisas a confirmar no jogo (seção 6)
antes de implementar.

## 1. Objetivo

Um terceiro foco por conta, além de **captura** e **ouro-xp-drop** (fase 3a): subir no ranking semanal de
capturas capturando **um de cada espécie** e passando para a próxima. O worker monta uma fila de hunts, da mais rápida para a
mais lenta, fica em cada uma com o `autoBallAteCapturar` até capturar e passa para a próxima.

## 2. O que já sabemos

- **`topCatchNova`** chega no mesmo frame do `bola` com `sucesso: true`, com `sp`, `chave`, `n`, `m`, `s` e
  `pontua`. Parece ser a entrada no ranking da semana; `pontua` sugere que nem toda captura pontua
  (provavelmente só a primeira de cada espécie na semana). Hoje é gravado como `battle.topCatchNova`, sem `data`.
- **`welcome.hunts[]`**: ~1.000 hunts com `area`, `nivel`, `especies[]` e `totalSpawns`. É o catálogo para
  planejar. O `welcome` inteiro fica no `raw` do `state.snapshot` a cada conexão.
- **Formato de `especies[]`** (pela referência DiuleJR/pokeidle-manager-online, não confirmado por nós):
  `{pokeId, nome, pontos}`, com `totalSpawns` na hunt. Numa hunt de uma espécie, `pontos` = `totalSpawns`
  (15), então `pontos / totalSpawns` deve ser a fração de spawns daquela espécie, que é o `P(spawn)` da conta
  da seção 3.2. O código da referência soma `pontos` de espécies de gerações diferentes na mesma hunt, o que
  indica que **existem hunts com mais de uma espécie**; nas iniciais de Kanto é uma só. Há também hunts com
  `especies` vazio (ex.: `lapras`, `totalSpawns: 5`), provavelmente especiais.
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

### 3.2 Roteiro de hunts (decidido em 13/11)

A estratégia é uma **fila de hunts**, não uma escolha contínua:

1. No começo da semana (ou quando o plugin sobe), monta a lista de **todas as espécies disponíveis** nas
   hunts alcançáveis que ainda não pontuaram na semana.
2. Ordena as hunts pela **mais rápida de render a captura** e monta a fila.
3. Vai para a primeira hunt da fila e fica nela com o **`autoBallAteCapturar`** ligado.
4. Quando captura (as espécies que faltavam naquela hunt), passa para a **próxima hunt** da fila.

Para ordenar, "mais rápida" é o **tempo esperado até a captura**, que junta o ritmo de abates com a chance
de a espécie aparecer e de a bola pegar:

```
horas até capturar(s, H) ≈ 1 / (abates/h em H × P(spawn de s em H) × P(captura de s com a bola))
```

- `abates/h`: medido quando a conta já passou pela hunt; senão, estimado pelo nível da hunt e da conta
  (e corrigido à medida que o worker mede).
- Numa hunt com uma espécie só, isso é basicamente o ritmo de abates dividido pela chance de captura. Numa
  hunt com várias espécies que faltam, conta o tempo até pegar todas, e uma hunt pode resolver várias de uma vez.
- Se uma espécie aparece em mais de uma hunt, ela entra só na hunt em que sai mais rápido.

**Proteções:**
- **Tempo máximo por hunt**: se passar de `max_hunt_factor` × o tempo esperado (ex.: 3×), pula para a
  próxima e deixa a espécie para o fim da fila.
- Recalcula a fila quando a conta sobe de nível (hunts novas ficam alcançáveis) ou quando uma captura
  acontece fora da ordem.
- Quando a fila acaba, cai para o foco `fallback` (ex.: captura ou ouro-xp-drop) até a semana virar.

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
