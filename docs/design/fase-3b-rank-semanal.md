# Fase 3b — foco "rank semanal" (rascunho)

Status: **rascunho**, 13/11/2026. As regras do Top Catch e do "Lançar até Capturar" foram confirmadas pela wiki
do jogo ([regras-do-jogo.md](../regras-do-jogo.md#da-wiki-do-jogo-13112026)). Uma espécie por hunt
confirmada pelo catálogo. Faltam o protocolo do `hunt.select`, o aviso do fim do "até capturar" e as decisões
da seção 7.

## 1. Objetivo

Um terceiro foco por conta, além de **captura** e **ouro-xp-drop** (fase 3a): subir no ranking semanal de
capturas capturando **um de cada espécie** e passando para a próxima. O worker monta uma fila de hunts, da mais rápida para a
mais lenta, fica em cada uma com o `autoBallAteCapturar` até capturar e passa para a próxima.

## 2. O que já sabemos

**Pelo catálogo do `welcome` (consultado em 13/11):** as **1.043 hunts têm exatamente uma espécie cada**, do
nível 1 ao 160.300. Então cada hunt da fila vale uma espécie, e o Lançar até Capturar desligar na primeira
captura é exatamente o sinal de "pronto, próxima hunt". A mesma espécie pode aparecer em mais de uma hunt
(níveis diferentes); entra na fila só a mais rápida.

**Pela wiki do jogo (confirmado):**

- O Top Catch conta **espécies diferentes capturadas com bola na semana**; vira no **sábado às 23h59 de Brasília**
  e paga 50/20/5 💎 para 1º, 2º–10º e 11º–100º. A espécie conta de novo a cada semana.
- O **Lançar até Capturar** desliga na **primeira captura**, de qualquer espécie. Numa hunt de uma espécie isso
  é exatamente o que queremos: capturou, troca de hunt e religa (`auto.set`). Numa hunt de várias espécies, ele
  pararia também numa espécie que já pontuou na semana.
- A chance de captura depende só do estágio evolutivo e da bola (tabela em regras-do-jogo.md). Com Ultra Ball,
  a média é ~68 abates para o 1º de três, ~85 para o meio (ou 1º de dois) e ~106 para a última forma.
- Trocar de área tem espera de 10 s, e a área nova fica vazia se você trocou dano nos 10 s anteriores.
- O **Safari** (60 min, cada aparição sorteada entre 985 espécies) é, de longe, o jeito mais rápido de somar
  espécies novas; o ticket se negocia no Mercado. Fica como ideia para depois (seção 7).

**Pelo protocolo e pela referência:**


- **`topCatchNova`** (confirmado em 14/11) chega no mesmo frame do `bola` com `sucesso: true`: `s` = início da
  semana (domingo), `sp` = espécie, `n` = espécies da semana já contando esta, `m` = minutos desde o início da
  semana (desempate), `pontua` = era nova na semana. A posição no ranking não vem. Hoje é gravado como
  `battle.topCatchNova`, sem `data`. Detalhes em [protocolo.md](../protocolo.md#observado-em-14112026-troca-de-hunt-e-lançar-até-capturar).
- **`welcome.hunts[]`**: ~1.000 hunts com `area`, `nivel`, `especies[]` e `totalSpawns`. É o catálogo para
  planejar. O `welcome` inteiro fica no `raw` do `state.snapshot` a cada conexão.
- **Formato de `especies[]`** (pela referência DiuleJR/pokeidle-manager-online, não confirmado por nós):
  `{pokeId, nome, pontos}`, com `totalSpawns` na hunt. Numa hunt de uma espécie, `pontos` = `totalSpawns`
  (15), então `pontos / totalSpawns` deve ser a fração de spawns daquela espécie, que é o `P(spawn)` da conta
  da seção 3.2. O código da referência soma `pontos` de espécies de gerações diferentes na mesma hunt, o que
  indica que **existem hunts com mais de uma espécie**; nas iniciais de Kanto é uma só. Há também hunts com
  `especies` vazio (ex.: `lapras`, `totalSpawns: 5`), provavelmente especiais.
- **`estado.dexMud`**: capturas (`c`) e abates (`k`) por espécie, mas de sempre, não da semana.
- **`hunt.select {slug}`** troca de hunt (confirmado em 14/11), só fora da trava de combate
  (`estado.centroLivreEm`; cada golpe recebido renova a trava). Vai direto de uma hunt para outra, sem passar
  pelo Centro. A resposta traz `batalha` `k:"hunt"` com `trocaLivreEm` (+10 s até a próxima troca); o
  `estado.huntSlug` só vem quando muda, então a hunt atual sai do `k:"hunt"`.
- **Lançar até Capturar** (confirmado em 14/11): na captura, o servidor manda um `estado` com
  `automation.autoBallAteCapturar: false`. É o sinal para o plugin trocar de hunt e religar com `auto.set`.
- **`ball.throw {ballId, slot}`** joga uma bola num selvagem abatido: janela de ~30 s, ~1,3 s entre
  arremessos. Ainda não confirmado. É o que permite jogar bola **só** nas espécies que faltam, em vez da bola
  automática, que joga em todo selvagem.
- Captura: `captura` do `welcome` (`base`, `piso`, `teto`, `porDegrau`) e `catchRate` das bolas (×1 a ×4).
  Em Magikarp, Poké Ball ≈ 0,3% e Ultra Ball ≈ 1,2% por arremesso.
- Bola automática exige VIP; `ball.throw` manual provavelmente não (a confirmar).

## 3. Como funcionaria

### 3.1 Estado da semana

- **Espécies que já pontuaram na semana**: dos `topCatchNova` com `pontua: true` da semana atual (campo `s`,
  domingo 00:00 de Brasília). Na subida do plugin, lê os eventos da semana em `events` (como o teto do
  `restock` faz). Se o jogo mandar a lista da semana no `welcome`, usa ela e dispensa o histórico.
- **Faltam**: espécies que aparecem em hunts alcançáveis e ainda não pontuaram.

### 3.2 Roteiro de hunts (decidido em 13/11)

A estratégia é uma **fila de hunts**, não uma escolha contínua:

1. No começo da semana (ou quando o plugin sobe), monta a lista de **todas as espécies disponíveis** nas
   hunts alcançáveis que ainda não pontuaram na semana.
2. Ordena as hunts pela **mais rápida de render a captura** e monta a fila.
3. Vai para a primeira hunt da fila e fica nela com o **`autoBallAteCapturar`** ligado.
4. Quando captura (as espécies que faltavam naquela hunt), passa para a **próxima hunt** da fila.

Como toda área tem o mesmo ritmo de ondas, o que muda o abate/hora entre hunts é a força do time contra elas
(nível da hunt abaixo do treinador, vantagem de tipo). E a chance de captura só depende do estágio: espécies
básicas (1º de três) saem ~1,5× mais rápido que formas finais.

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
- Custo médio por espécie (bolas ÷ chance): Poke Ball 1,4 mil–1,7 mil de ouro, Great Ball 2,7 mil–4,3 mil,
  Ultra Ball 8,9 mil–13,8 mil, conforme o estágio. A Poke Ball é a mais barata por captura, mas leva ~4× mais
  abates (tempo). Com o ouro de hunts baixas (41 por abate em Magikarp), Ultra Ball não se paga.

### 3.4 Quem manda em quê

O `auto.set` e as compras não podem ter dois donos. Proposta:

- O `restock` ganha o foco `rank`: **não** mexe nas flags de bola; mantém estoque das bolas de `rank_balls`
  (a escolhida pela `rank_ball_rule` primeiro) e das poções.
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

1. ~~Como funciona o ranking~~: respondido pela wiki (seção 2).
2. ~~`topCatchNova`~~ (14/11): `s` início da semana, `sp`/`chave` espécie, `n` espécies da semana, `m` minutos
   desde o início da semana, `pontua` nova na semana. Falta: o `m` e o `ini` do `estado.topCatch`, e se o
   `welcome` traz o `topCatch` com a lista das espécies da semana (dispensaria ler o histórico).
3. ~~`hunt.select`~~ (14/11): resposta com `campo.init`, `batalha` `k:"hunt"` (`trocaLivreEm` +10 s) e
   `estado`. Falta ver o erro de trocar durante a trava ou antes do `trocaLivreEm`.
4. ~~`autoBallAteCapturar`~~ (14/11): na captura vem um `estado` com a `automation` e a flag em `false`.
5. ~~Hunts alcançáveis~~: pelo nível do treinador por região (wiki). Troca direta entre hunts confirmada
   (Meowth → Machop); entre regiões diferentes ainda não testado.
6. ~~Catálogo~~: 1.043 hunts, uma espécie cada (13/11). Desde o tradutor v2 o `welcome` não grava mais as
   tabelas do jogo; a 3b vai gravar o catálogo numa tabela própria, só quando mudar. Consulta original (não tem token nem dado da conta):
   ```sql
   select jsonb_pretty(raw->'hunts'->0) as exemplo, jsonb_array_length(raw->'hunts') as total,
          jsonb_pretty(raw->'captura') as captura
     from public.events where type = 'state.snapshot' order by received_at desc limit 1;
   ```

## 7. Decisões

**Tomadas em 13/11:**

- **Bolas parametrizáveis.** A config do foco rank tem a lista de bolas permitidas (`rank_balls`, em ordem de
  preferência) e a regra de escolha (`rank_ball_rule`):
  - `se_paga` (padrão): a melhor bola permitida cujo preço cabe no ouro líquido por abate da conta, a mesma regra
    do foco captura. Na prática, a Ultra entra quando o abate rende ≥ 130 de ouro, que é quando a conta abate
    rápido em hunt alta; em hunt baixa, cai para Great ou Poke.
  - `fixa`: sempre a primeira da lista com estoque.
  O `weekly_ball_budget` continua como teto.
- **Foco escolhido no painel.** Na página da conta (`/contas/<id>`), um seletor de foco (captura, ouro-xp-drop,
  rank) que manda os `plugin.set` certos: o foco do `restock` e o `rank` ligado ou desligado. Os parâmetros do
  rank (bolas, regra, orçamento, fallback) ficam no mesmo lugar.

**Em aberto:**

- Quais contas ficam no foco `rank`: decide-se no painel, conta por conta.
- Valor padrão do `weekly_ball_budget`.
- Foco de volta quando acabarem as espécies alcançáveis (`fallback`).
- **Safari Ticket**: comprar no Mercado e usar uma vez por semana pode render dezenas de espécies numa hora.
  Vale avaliar quando a fase 7 (preços do Mercado) estiver pronta.
- Se vale capturar espécies que só aparecem em hunts acima do nível da conta subindo de nível antes
  (fica fora da 3b; seria um plano de várias semanas).

## 8. Ordem de implementação

1. Confirmar a seção 6 e fechar a seção 7.
2. Tradutor: `topCatchNova` com `data` (`species`, `pontua`, ...) e `hunt.changed` confiável.
3. Catálogo de hunts a partir do `welcome` + estimador de `novas/h`, com testes.
4. Plugin `rank` em `observe_only`: grava `rank.plan` e as ações que faria. Conferir por alguns dias.
5. `ball.throw` ligado, depois `hunt.select`.
6. Métricas e card no painel.
