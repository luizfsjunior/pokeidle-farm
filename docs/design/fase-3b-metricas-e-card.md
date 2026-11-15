# Fase 3b: métricas e card do rank (passo 6)

Status: **rascunho v2**, 15/11/2026. Decisões D-K a D-N tomadas em 15/11 (fim do documento); falta aprovar a
spec e os casos de teste.

É o último passo da [ordem de implementação da 3b](fase-3b-rank-semanal.md#8-ordem-de-implementação). Com o
`rank` agindo ([passo 5](fase-3b-rank-ligado.md)), falta ver no painel como a semana está indo sem abrir o SQL:
quantas espécies pontuaram, onde a conta está, qual é o próximo alvo e se algo está travado.

## Proposta

### 1. Métrica `rank_points`

Base nova em `metric_definitions`, somada no `refresh_metric_hourly` como as outras:

| `key` | `label` | `unit` | Origem |
|---|---|---|---|
| `rank_points` | Espécies novas na semana | `espécies` | `count(*)` dos `rank.catch` com `scores = true`, por hora e hunt (o `rank.catch` já traz `hunt_slug`) |
| `rank_points_per_hour` | Espécies novas por hora ativa | `espécies/h` | razão `rank_points` ÷ `active_minutes` × 60 |

- A migration recria o `refresh_metric_hourly` com a coluna nova (mesmo padrão do `ouro_liquido`) e recalcula
  desde 2026-11-14, quando o `rank.catch` começou a ser gravado.
- Soma de `rank_points` numa semana = espécies que pontuaram **enquanto o worker estava conectado**. Uma captura
  feita jogando à mão, com o worker desligado, não entra; o número oficial da semana vem do jogo (seção 2).
- Isso já resolve o objetivo do tipo `metric` previsto no desenho da 3b: `rank_points` com `starts_at` no domingo
  00:00 e `deadline` no sábado 23:59 de Brasília. Por isso o `rank_species_week` sai (D-K).

### 2. Card "Rank semanal" na página da conta

Aparece quando o plugin `rank` está ligado, logo abaixo do card "Foco". Lido direto de `events` (o RLS
`own_events` já deixa o dono ler), só da semana atual (desde domingo 00:00 de Brasília):

| Linha | Origem |
|---|---|
| **Posição** | último `rank.position` (seção 5): "12º", ou "fora do top 100, faltam N espécies" |
| **Espécies na semana** | o maior `week_species` dos `rank.catch` e `rank.week` da semana (o número do jogo, que conta também as capturas feitas à mão) |
| **Agora** | último `rank.plan`: `current_hunt` → alvo (`target.slug`, `target.hours` em minutos), bola, `reason` e há quanto tempo |
| **Modo** | último `rank.mode` (ativo ou fallback) e se o `rank` está em ensaio (`dry_run`) |
| **Fila** | `queue_len` e os 5 primeiros da `queue` do último `rank.plan` (hunt e minutos esperados) |
| **Puladas** | `skipped` do último `rank.plan`, com o nome das espécies (pela `queue` ou pelo slug) |
| **Problemas** | os `rank.failed` das últimas 24 h (motivo e hunt) e o `degraded` do último `rank.plan` |
| **Ritmo** | `rank_points_per_hour` da semana (da `metric_hourly`) |

Sem nada da semana ainda: "sem dados desta semana".

O card usa o `AutoRefresh` que já existe (a cada 30 s com a página aberta).

### 3. Visão geral

Na tela inicial, o card de cada conta com `rank` ligado ganha uma linha: "Rank: N espécies · alvo X". Mesma origem
da seção 2 (só as duas consultas mais leves).

### 4. Abates/h das hunts visitadas (D-M)

Hoje uma hunt só vira "medida" com `min_active_minutes` (30) nela nos últimos 14 dias. Com o rank passando ~8 min
em cada hunt, quase nenhuma vai virar medida e a fila continua usando o ritmo padrão da conta para todas. Proposta:
baixar o padrão de `min_active_minutes` para 5. Com ~1.000 abates/h, 5 min são ~80 abates, o bastante para
separar uma hunt de 600/h de uma de 1.200/h.

### 5. Posição no ranking (D-N)

O `topCatch` não traz a posição (`meu` vem `null`, `campeoes` é o pódio da semana anterior). Lendo o `app.js`
público do jogo (v1.420.0, 15/11), a tela do Top Catch calcula a posição **no próprio cliente** (`tcPosicaoCom`):

- Pede `{"t":"ranking.pedir","aba":"capturas"}`. A resposta é
  `{"t":"ranking","aba":"capturas","semana":"2026-11-15","linhas":[{nick, level, valor, looktype, vs, rank}]}`,
  com `valor` = espécies na semana. A lista vai até o último premiado (top 100, `PREMIADOS_TOP_CATCH`).
- Se o meu nick está na lista com o `valor` igual ao meu `n`: posição = índice + 1.
- Senão: posição = 1 + quantos da lista têm `valor > n`, ou `valor == n` e `level ≥` o meu (o desempate é pelo
  nível). Se isso passar do tamanho da lista, a conta está **fora** do top 100, e o jogo mostra quantas espécies
  faltam para o corte: `valor` da última linha − `n` + 1.

Proposta:

- **Ação nova `RankingRequest`** (`ranking.pedir`, `aba: "capturas"`, só leitura, intervalo mínimo 5 min). O
  plugin `rank` manda na subida e depois de cada `rank.catch` que pontua (o rate limiter segura as repetidas;
  o navegador pede a cada minuto com a tela aberta). Como o `topcatch.pedir`, vai mesmo com `dry_run`.
- **Tradutor**: `ranking` com `aba: "capturas"` vira `rank.board` (**não gravado**: ~100 linhas por resposta),
  com `week_start` (o `semana`) e `rows` (`nick`, `level`, `valor`). Outras abas continuam ignoradas.
- **Plugin `rank`**: no `rank.board` da semana atual, calcula a posição com a regra acima, usando o `ctx.nick`,
  o nível da conta e o `n` mais recente (`week_species` do último `rank.catch`/`rank.week`), e grava
  **`rank.position`**:
  ```json
  {"week_start": "2026-11-15", "species": 4, "position": 812, "inside": false, "list_size": 100,
   "cutoff": 41, "missing": 38, "above": {"nick": "...", "valor": 5}}
  ```
  Fora do top 100: `position: null`, `inside: false` e `missing` = espécies que faltam para entrar. Dentro:
  `position`, `inside: true`, `missing: 0`. Só grava quando algo muda (posição, `species` ou `cutoff`).
- O card e a linha da visão geral leem o último `rank.position` da semana.

## Fora deste passo

- Card de rank para várias contas comparadas, histórico de semanas anteriores.
- Posição exata fora do top 100 (o jogo não manda as linhas abaixo do corte).

## Decisões (tomadas em 15/11)

- **D-K.** `rank_species_week` sai: o número da semana vem do jogo no card, e o objetivo usa `rank_points`.
- **D-L.** Card na página da conta e linha na visão geral.
- **D-M.** `min_active_minutes` padrão passa de 30 para 5.
- **D-N.** Tentar a posição pelo `ranking.pedir` da aba `capturas`, com a mesma conta que o cliente do jogo faz
  (seção 5). Se a resposta real não bater com o que o `app.js` sugere, fica de fora sem prejuízo do resto.

## Casos de teste propostos

SQL (`supabase/tests/rank_points_test.sql`, Postgres local com as migrations):

1. Dois `rank.catch` com `scores: true` e um com `scores: false` na mesma hora e hunt → `rank_points` = 2 nessa
   hora e hunt; nenhuma linha para o `false`.
2. `rank.catch` sem `hunt_slug` → conta em `hunt_slug = ''`.
3. `rank_points_per_hour` pelo `metric_series`: 2 pontos em 30 min ativos → 4/h.
4. As métricas que já existiam não mudam (mesma conta do `ouro_liquido_test.sql`).

Worker (`test_rank_plugin.py`), se D-M for aceita:

5. `RankConfig().min_active_minutes == 5`; hunt com 6 min ativos conta como medida, com 4 não.

Posição (`test_rank_plugin.py` e `test_protocol.py`/tradutor), com o nick `farm1` nível 150:

9. `RankingRequest` → wire `{"t":"ranking.pedir","aba":"capturas"}`, `min_interval_s == 300`; sai na subida e
   depois de um `rank.catch` que pontua; com `dry_run` também.
10. Tradutor: `ranking` `aba: "capturas"` → `rank.board` com `week_start` e `rows`, em `NOT_PERSISTED`
    (não gravado); `aba: "nivel"` → nada.
11. Na lista com o `valor` igual ao `n` → `position` = índice + 1, `inside: true`, `missing: 0`.
12. Fora da lista, empate: `n = 5`, linhas com `valor` 9, 5 (nível 200) e 5 (nível 100) → `position` 3 (o de nível
    200 fica na frente, o de nível 100 atrás).
13. Fora do top: lista de 100 linhas, a última com `valor` 41, `n = 4` → `position: null`, `inside: false`,
    `cutoff: 41`, `missing: 38`.
14. `rank.board` de outra semana → ignorado; o mesmo resultado duas vezes → um `rank.position` só.

Painel (sem framework de testes: `npm run typecheck`, build e conferência no navegador com a conta real):

6. Card com os dados da semana: espécies e posição batendo com a tela do Top Catch do jogo, alvo e fila iguais ao
   último `rank.plan`.
7. Semana sem eventos → "sem dados desta semana".
8. `rank` desligado → sem card.
