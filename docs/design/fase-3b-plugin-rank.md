# Fase 3b: plugin `rank` em modo de ensaio (passo 4)

Status: **implementado** (14/11/2026), decisões D-A a D-D tomadas. Código em `worker/src/pokeidle_farm/plugins/rank.py`,
`HuntSelect` em `actions.py`, `rank_hunt_stats` nos stores e na migration `20261115000000_rank_hunt_stats.sql`.
Testes em `worker/tests/test_rank_plugin.py` (casos 1 a 20) e `supabase/tests/rank_hunt_stats_test.sql` (caso 21).

Diferenças do texto abaixo para o que foi implementado:
- Os plugins continuam vivos entre reconexões, então a sessão passou a atualizar o `ctx.catalog` dos plugins que
  estão rodando a cada `welcome` com hunts (antes o catálogo do contexto ficava o da primeira conexão). O
  `topcatch.pedir` sai na subida e a cada `session.connected`.
- No timeout, o alvo é zerado antes de replanejar: se a espécie pulada continua sendo a única da fila, ela volta
  como alvo com o tempo recomeçando (sem isso, ela estouraria de novo a cada abate).
- A virada da semana também é percebida pelo relógio (no primeiro abate depois de domingo 00:00 de Brasília),
  não só por um `rank.catch` de semana nova; nesse caso o plugin pede o `topcatch.pedir` de novo.
- O ritmo padrão da conta e o abates/h por hunt só contam hunts que existem no catálogo. Na primeira subida
  real, a conta tinha eventos do simulador (hunts `sim-*`, ~360/h) que puxariam o padrão para ~390/h, contra
  ~1.000/h medidos no Magikarp.
- O `rank.would` repete quando a entrada da ação muda (alvo ou bola novos, ou `automation` diferente), não a cada
  plano.

É o passo 4 da [ordem de implementação da 3b](fase-3b-rank-semanal.md#8-ordem-de-implementação). Junta as peças
do passo 3 ([catálogo e fila](fase-3b-catalogo-e-fila.md)) num plugin que decide, a cada momento, **em qual hunt a
conta deveria estar** e **o que mandaria para o jogo**, sem mandar nada que mude o estado da conta. Serve para
conferir a fila e os gatilhos com dados reais por alguns dias antes do passo 5 (ligar `hunt.select` e o Lançar
até Capturar de verdade).

## O problema do "observe_only"

O `ACTION_MODE` vale para o worker inteiro, e no PC de casa ele está em `enabled` desde a fase 3a (o `restock`
compra e manda `auto.set` de verdade). Então o ensaio não pode depender do `ACTION_MODE`: o plugin `rank` tem
uma flag própria, **`dry_run`** (padrão `true`). Com ela ligada, em vez de chamar `ctx.actions.submit` ele
registra `rank.would` com a ação e o motivo. A única exceção é o `topcatch.pedir`, que é só leitura (D-A).

## Proposta

### 1. Config (`RankConfig`, `extra="forbid"`)

| Campo | Padrão | Uso |
|---|---|---|
| `dry_run` | `true` | não manda `hunt.select` nem `auto.set`; registra `rank.would` |
| `rank_balls` | `[4, 3, 2, 1]` | bolas permitidas, em ordem de preferência (Ultra, Super, Great, Poke) |
| `rank_ball_rule` | `"se_paga"` | `se_paga` ou `fixa` ([fase-3b-rank-semanal.md, seção 7](fase-3b-rank-semanal.md#7-decisões)) |
| `window_kills` / `min_kills` | `200` / `50` | janela de abates para o ouro líquido por abate (igual ao `restock`) |
| `max_hunt_factor` | `3.0` | pula a hunt alvo depois de `fator × horas esperadas` sem capturar |
| `min_hunt_minutes` | `10` | piso do tempo acima, para hunts de captura muito rápida |
| `history_days` | `14` | quanto do histórico entra no abates/h por hunt e na chance observada |
| `min_active_minutes` | `30` | minutos ativos mínimos para o abates/h de uma hunt contar como medido |
| `default_kills_per_hour` | `300` | ritmo usado quando a conta não tem histórico nenhum |
| `queue_preview` | `10` | quantas hunts da fila vão no `rank.plan` |

`weekly_ball_budget` e `fallback` ficam para o passo 5 (só fazem sentido quando o plugin age).

### 2. Subida (`start`)

1. Sem `ctx.catalog` (ou sem hunts): registra `rank.plan` com `reason: "sem_catalogo"` e fica parado até o
   próximo `state.snapshot` (que traz o `welcome` de novo).
2. **Semana atual**: `week_start` = domingo 00:00 de Brasília (UTC−3, sem horário de verão) da data de agora,
   no formato do jogo (`"2026-11-08"`).
3. **Espécies que já pontuaram**: o `rank.week` mais recente com esse `week_start` (as chaves de `species`) mais
   os `rank.catch` com `scores: true` e o mesmo `week_start` recebidos depois dele. Sem `rank.week`, só os
   `rank.catch`. Lidos com `store.recent_events` desde o `week_start`.
4. **Ritmo e chance por hunt**: uma consulta nova, `store.rank_hunt_stats(account_id, since)` (D-B), que devolve
   por hunt os abates e minutos ativos (do `metric_hourly`) e a última `chance` e `ball_id` de `capture_attempt`
   com `chance` (dos `events`). Daí saem o `kills_per_hour` medido (só hunts com `min_active_minutes`), o
   `default_kills_per_hour` da conta (todos os abates ÷ todos os minutos ativos × 60, ou o da config sem
   histórico) e as `observed_chances`.
5. Manda `TopCatchRequest` (o pedido pode ser barrado pelo rate limiter de 5 min; tudo bem).
6. Planeja (seção 3) com `reason: "start"`.

Se alguma leitura do banco falhar, segue sem ela (como o `restock`), com um aviso no log, e o `rank.plan`
marca `degraded: [...]` com o que faltou.

### 3. Planejar

`plan_queue(ctx.catalog, ctx.species, nível, pontuadas, bola, kph, kph_padrão, chances)` do passo 3, com:

- **Bola**: a de `rank_ball_rule`. `fixa` → a primeira de `rank_balls` com estoque (`ctx.state.balls`), ou a
  primeira da lista se nenhuma tiver. `se_paga` → a primeira de `rank_balls` cujo preço cabe no ouro líquido
  por abate da janela; sem `min_kills` abates na janela, cai na regra `fixa`; se nenhuma se paga, a mais barata
  da lista.
- **Pulada**: espécies puladas por tempo (seção 4) vão para o fim da fila, na ordem em que foram puladas.
- **Alvo**: o primeiro da fila. Se a conta já está numa hunt da fila e o alvo novo não é pelo menos 10% mais
  rápido que ela, o alvo é a hunt atual (D-C, para não trocar de hunt à toa).

Cada planejamento registra **`rank.plan`** (gravado):

```json
{"reason": "start", "dry_run": true, "week_start": "2026-11-08", "scored": 12,
 "trainer_level": 150, "ball_id": 4, "current_hunt": "magikarp",
 "target": {"slug": "caterpie", "species_id": 10, "hours": 0.068, "chance": 0.0146,
            "kills_per_hour": 1000, "chance_source": "stage", "kph_known": false},
 "queue_len": 187, "queue": [ ...até queue_preview itens, mesmo formato do target... ],
 "skipped": [77], "degraded": []}
```

`reason`: `start`, `week` (chegou `rank.week`), `captured` (pontuou a espécie alvo), `captured_other` (pontuou
outra espécie da fila), `level_up`, `timeout`, `week_rollover`, `ball_changed`, `sem_catalogo`.
Fila vazia → `target: null` e nenhuma ação.

### 4. Gatilhos

| Evento | O que faz |
|---|---|
| `rank.week` da semana atual | troca as pontuadas pelas do evento (mais os `rank.catch` posteriores) e replaneja (`week`) |
| `rank.catch` com `scores: true` | soma a espécie; se for a do alvo → `captured`, senão, se estava na fila → `captured_other` |
| `rank.catch` com `week_start` mais novo que o atual | zera as pontuadas e as puladas (`week_rollover`) |
| `auto.catch_until_capture_off` | só registra no próximo `rank.plan` (`catch_until_off_at`); a confirmação de que pontuou vem do `rank.catch` |
| `state.patch` / `state.snapshot` com nível maior | replaneja (`level_up`) |
| `hunt.changed` | atualiza a hunt atual; se for o alvo, marca o início do tempo no alvo |
| `kill` | alimenta a janela de ouro; confere o tempo no alvo (abaixo) e a troca de bola |

**Tempo no alvo**: conta a partir do momento em que a conta entrou na hunt alvo (em `dry_run`, a partir de
quando o alvo foi escolhido, já que a conta não vai até lá). Passou de
`max(max_hunt_factor × hours, min_hunt_minutes)` sem pontuar → a espécie vai para `skipped` e replaneja
(`timeout`).

**Troca de bola**: se a regra passa a escolher outra bola, replaneja (`ball_changed`), no máximo uma vez a cada
`window_kills` abates.

### 5. O que faria

Depois de cada `rank.plan` com alvo:

1. Se a hunt atual não é o alvo → `HuntSelect(slug)` (ação nova, wire `{"t":"hunt.select","slug":...}`,
   intervalo mínimo 5 min).
2. Se a `automation` não tem `autoBallAteCapturar: true` com a bola escolhida na frente de `ballIds` e
   `autoBallSemParar: false` → `AutoSet` com isso (o objeto inteiro, como o `restock` faz).

Com `dry_run`, cada um vira `rank.would` (gravado) com `{action, input, reason}`, e o plugin passa a considerar
a ação "feita" para não repetir o mesmo `rank.would` a cada abate (repete só se o alvo ou a bola mudar). Sem
`dry_run` o código chama `ctx.actions.submit`, mas o passo 4 não liga isso (o passo 5 revisa a trava de combate
e o `switch_free_at` antes).

### 6. Supabase

Migration nova com a função `rank_hunt_stats(p_account uuid, p_since timestamptz)` (`security definer`, só para
a service role), que devolve `hunt_slug, kills, active_minutes, last_chance, last_ball_id`:

- `kills` e `active_minutes`: soma de `metric_hourly` por `hunt_slug` (sem `''`) desde `p_since`.
- `last_chance`, `last_ball_id`: `distinct on (data->>'hunt_slug')` dos `capture_attempt` com `chance`, do mais
  recente.

`MemoryStore` implementa o mesmo a partir dos eventos guardados em memória (abates contam um minuto ativo por
minuto distinto com abate).

### Fora deste passo

- `hunt.select` e `auto.set` de verdade, trava de combate, `switch_free_at`, `weekly_ball_budget`, `fallback`:
  passo 5.
- O foco `rank` no `restock` e o seletor de foco no painel: passo 5.
- Métricas `rank_points`/`rank_species_week` e o card no painel: passo 6.

## Decisões (tomadas em 14/11)

- **D-A. `topcatch.pedir` mesmo com `dry_run`**: sim, porque é só leitura e sem ele a fila não sabe
  quais espécies já pontuaram antes do worker subir. Continua respeitando o `ACTION_MODE` (D6 do passo 3).
- **D-B. Consulta nova `rank_hunt_stats` (função no banco)** em vez de `recent_events`. Motivo: o
  `recent_events` traz no máximo 1.000 linhas, do mais antigo ao mais novo, e com a bola automática ligada são
  milhares de `capture_attempt` por dia; os abates por hunt já estão agregados no `metric_hourly`.
- **D-C. Histerese de 10%** para não trocar de hunt quando a diferença é pequena. Vale também no `dry_run`, para
  o ensaio mostrar o comportamento real.
- **D-D. Padrões da config**: `rank_balls = [4, 3, 2, 1]` (a Super Ball, id 3, custa 50 e pega ×3: fica entre a Great e a Ultra no custo
  e no tempo, e é o degrau da regra `se_paga` quando o abate rende de 50 a 129 de ouro líquido) e
  `default_kills_per_hour = 300` (o medido até agora é ~360/h).

## Casos de teste propostos

Em `worker/tests/test_rank_plugin.py`, com `MemoryStore`, gateway falso, relógio controlado e um catálogo de
4 hunts (Caterpie nível 1, Metapod 5, Magikarp 10, Treecko 500) mais a Pokedex delas.

Subida:

1. **Sem catálogo** → um `rank.plan` com `reason: "sem_catalogo"`, `target: null`; nenhum `rank.would`.
2. **Subida normal** (nível 150, sem histórico) → `TopCatchRequest` enviado; `rank.plan` com `reason: "start"`,
   alvo Caterpie (`first_of_three`, mais rápida), Treecko fora da fila (nível 500); `rank.would` com
   `hunt.select {"slug": "caterpie"}` e um `auto.set` com `autoBallAteCapturar: true`, `autoBallSemParar: false`
   e `ballIds[0] == 4`.
3. **Pontuadas na subida**: `rank.week` da semana com `{"10": 9502}` e um `rank.catch` posterior com
   `species_id: 129, scores: true` → Caterpie e Magikarp fora da fila; alvo Metapod. Um `rank.week` de semana
   anterior é ignorado.
4. **Semana em Brasília**: com o relógio em sábado 2026-11-14 23:30 de Brasília, `week_start == "2026-11-08"`;
   em domingo 2026-11-15 00:10 de Brasília (03:10 UTC), `"2026-11-15"`.
5. **Ritmo medido**: `rank_hunt_stats` com Magikarp 2.000 abates em 60 min ativos → `kills_per_hour` 2.000,
   `kph_known: true`; uma hunt com 20 min ativos não conta como medida. O padrão vira o total da conta.
6. **Chance observada**: `last_chance 0.02` com Ultra na Metapod → `chance_source: "observed"`.
7. **Banco falhando** (store que levanta exceção) → `rank.plan` sai com `degraded` preenchido, sem exceção.

Gatilhos:

8. **Captura do alvo**: `rank.catch {species_id: 10, scores: true}` com alvo Caterpie → `rank.plan`
   `reason: "captured"`, alvo novo, novo `rank.would` de `hunt.select`.
9. **Captura sem pontuar** (`scores: false`) → nada muda.
10. **Captura de outra da fila** → `captured_other`, alvo igual, sem `rank.would` novo.
11. **`rank.week` chega depois da subida** → `reason: "week"`, pontuadas substituídas.
12. **Virada da semana**: `rank.catch` com `week_start` novo → `week_rollover`, pontuadas = só a do evento, puladas
    zeradas.
13. **Subiu de nível** (patch com nível 600) → `level_up`, Treecko entra na fila.
14. **Timeout**: alvo com `hours` 0,1, `max_hunt_factor` 3 e `min_hunt_minutes` 10 → um `kill` aos 17 min não faz
    nada; aos 19 min → `timeout`, a espécie vai para `skipped` e para o fim da fila.
15. **Histerese**: conta já na Metapod (na fila); Caterpie só 5% mais rápida → alvo continua Metapod, sem
    `hunt.select`; 15% mais rápida → troca.
16. **Sem repetição**: 100 `kill` seguidos sem mudança → um único par de `rank.would`.
17. **Bola `se_paga`**: janela com 50 abates de 100 de ouro líquido → bola 3 (Super, 50 ≤ 100 < 130); com 30 →
    bola 2 (Great); com 200 → bola 4; mudança → `ball_changed`, uma vez só por janela.
18. **`dry_run: false` em `observe_only`** → as ações passam pelo gateway e viram `action.blocked`; nenhum
    `rank.would`.
19. **Config inválida** (campo desconhecido, `rank_balls` vazio) → plugin não sobe (degradado).

Ação e banco:

20. **`HuntSelect`** → wire `{"t":"hunt.select","slug":"caterpie"}`, `min_interval_s == 300`.
21. **`rank_hunt_stats` no Postgres local** (migration aplicada): soma por hunt sem `''`, respeita `p_since`, pega
    a `chance` mais recente por hunt e ignora `capture_attempt` sem `chance`.
