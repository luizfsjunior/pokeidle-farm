# Fase 3b: plugin `rank` agindo de verdade (passo 5)

Status: **implementado** (15/11/2026), decisões D-E a D-J tomadas (fim do documento). Código em
`worker/src/pokeidle_farm/plugins/rank.py` e `restock.py`, `focus.set` em `commands.py`, trava e relógio do
servidor em `plugins/base.py` (`AccountStateView`), migration `20261115010000_commands_focus_set.sql` e o card
`web/app/contas/[id]/FocusCard.tsx`. Testes: casos 22 a 37 em `test_rank_plugin.py`, 38 no caso 20, 39 a 42 e
47 em `test_restock.py`, 43 a 45 em `test_commands.py`, 46 em `test_session.py`.

Diferenças do texto abaixo para o que foi implementado:
- Sem `dry_run` mas com o `restock` em outro foco, o `rank` grava `rank.would` como no ensaio e não publica
  `rank.mode`.
- O `auto.set` também espera quando o gateway recusa (rate limit: o tempo que falta; `observe_only`:
  `retry_after_s`), para não gravar um `action.blocked` a cada abate. Quando o `estado` reflete o `auto.set`, a
  espera zera: a próxima queda da flag religa assim que o rate limiter (30 s) deixar.
- Se o rate limiter barra o `hunt.select` (ex.: menos de 20 s depois do anterior), o plugin tenta de novo quando
  ele deixar.

É o passo 5 da [ordem de implementação da 3b](fase-3b-rank-semanal.md#8-ordem-de-implementação). O passo 4
([plugin em ensaio](fase-3b-plugin-rank.md)) já decide a hunt alvo e grava o que faria. Aqui ele passa a mandar
`hunt.select` e `auto.set` de verdade, com `dry_run: false`, e o painel ganha o seletor de foco.

O texto original do passo 5 era "`ball.throw` ligado, depois `hunt.select`". O `ball.throw` saiu: o Lançar até
Capturar do jogo (confirmado em 14/11) faz o papel dele. Numa hunt de uma espécie, ele joga bola até a primeira
captura e desliga sozinho, então o plugin só precisa trocar de hunt e religar a flag. O `ball.throw` continua como
plano B (seção 3.3 do desenho da 3b).

## O que muda em relação ao ensaio

1. **Trava de combate e `trocaLivreEm`.** O `hunt.select` só sai quando o relógio do servidor passa da trava
   (`centroLivreEm`) e do `trocaLivreEm` da última troca.
2. **Confirmação da troca.** O `hunt.select` só conta como feito quando chega o `hunt.changed` com o slug pedido.
   Sem isso, ou com `erro` do jogo, tenta de novo com espera.
3. **Religar o Lançar até Capturar.** O servidor desliga a flag em toda captura; com alvo definido, o plugin religa.
4. **Dono do `auto.set`.** Com o foco `rank`, o `restock` não mexe nas flags de bola enquanto o `rank` tem alvo;
   só repõe o estoque da bola que o `rank` escolheu.
5. **Fila vazia**: o `restock` assume no foco de `fallback` (ouro-xp-drop por padrão). A conta nunca fica parada.
6. **Seletor de foco no painel**, com os parâmetros do rank.

## Proposta

### 1. Trava e relógio do servidor

Medido em 15/11 (12 `state.patch` com `centroLivreEm`, conta nível 16 no Magikarp): a trava fica de 2,4 s a 5 s à
frente do relógio do servidor depois de cada golpe recebido. Ou seja, abre entre um golpe e outro, sem precisar
ir ao Centro.

- O `AccountStateView` ganha `combat_free_at` (o `centro_livre_em` do patch, em ms do servidor, convertido para
  `datetime` UTC), `switch_free_at` (do último `hunt.changed`) e `server_offset` (servidor − local, que o tradutor
  já calcula pelo `servidorAgora`), mais um método `server_now()`. Para isso o `apply` passa a olhar também o
  `hunt.changed`, e a sessão copia o `server_offset` do tradutor para o `AccountStateView`.
- O plugin só manda o `HuntSelect` quando `server_now() ≥ max(combat_free_at, switch_free_at) + switch_margin_s`
  (padrão 0,5 s). Se ainda não pode, guarda o pedido e confere de novo a cada `kill`, `state.patch` e
  `hunt.changed` (o `field.tick` não, é ruído demais). Sem `server_offset` conhecido, usa o relógio local.

### 2. Confirmação, erro e nova tentativa

- Depois de mandar, espera o `hunt.changed` com o slug pedido por até `switch_confirm_s` (padrão 15 s), conferido
  a cada evento.
- Chegou: a hunt atual vira o alvo e começa a contar o tempo no alvo.
- Chegou `game.error` nesse intervalo, ou o prazo passou sem confirmação: registra `rank.failed`
  `{action: "hunt.select", slug, reason: "<chave do erro>" | "timeout"}` e tenta de novo depois de
  `switch_retry_s` (padrão 60 s). Na 3ª falha seguida para o mesmo alvo, a espécie vai para `skipped` (como no
  timeout) e o plugin replaneja com `reason: "switch_failed"`.
- O `game.error` que chegar com um `hunt.select` pendente é o primeiro registro que teremos do erro de trocar na
  trava; a chave entra no `protocolo.md` quando aparecer.
- O `rank` passa a assinar `game.error`.

**Intervalo (D-E)**: o `HuntSelect.min_interval_s` cai de 300 s para 20 s (cobre o `trocaLivreEm` de 10 s com
folga), e o plugin tem um teto, `max_switches_per_hour` (padrão 10), numa janela móvel de 1 h. Estourou o teto:
espera, com um `rank.plan` `reason: "switch_cap"` (uma vez por estouro).

### 3. Lançar até Capturar (D-J)

O `auto.set` desejado é o mesmo do ensaio: `ballIds` com a bola escolhida na frente, `autoBallAteCapturar: true`,
`autoBallSemParar: false` e o resto da `automation` atual.

- Sai **junto com o `hunt.select`**, sem esperar o `hunt.changed` e sem desligar a bola fora do alvo. Se a conta
  capturar uma espécie que já pontuou antes de chegar no alvo, o servidor desliga a flag e o plugin religa (abaixo).
  O custo é, no máximo, uma captura perdida por troca.
- **Religar**: sempre que há alvo e a `automation` observada difere da desejada (por exemplo, o servidor desligou
  a flag numa captura), o plugin manda o `auto.set` de novo.
- **Sem repetição**: o dedup do ensaio (`_sent`) passa a ser como o do `restock`. Não repete o mesmo `auto.set`
  enquanto espera o `estado` refletir, por até `retry_after_s` (padrão 60 s); se a `automation` continuar
  diferente depois disso, manda de novo.
- A captura do alvo chega como `rank.catch` com `scores: true`: replaneja (`captured`) e sai o `hunt.select` do
  alvo novo, com o `auto.set` religando a flag.

### 4. `restock` com foco `rank` e o fallback (D-F, D-H)

`RestockConfig.focus` ganha `"rank"` e o campo novo `fallback_focus: "gold_xp_drop" | "capture"` (padrão
`"gold_xp_drop"`, D-H), usado só com `focus: "rank"`.

O `rank` avisa o `restock` pelo barramento, com o evento **`rank.mode`** (gravado), em toda mudança de modo:

```json
{"mode": "active", "ball_id": 2}       // tem alvo: o rank é dono das flags de bola
{"mode": "fallback", "reason": "queue_empty"}   // sem alvo: o restock assume
```

Com `focus: "rank"`, o `restock`:

- **modo `active`** (ou antes do primeiro `rank.mode`): nunca manda `auto.set`; repõe poções e revives como hoje e
  repõe a bola do `ball_id` do último `rank.mode`, com o `ball_min`/`ball_target` de sempre.
- **modo `fallback`**: age exatamente como o `fallback_focus` (`gold_xp_drop` desliga as flags de bola e não compra
  bola; `capture` escolhe a bola pelo ouro líquido e liga o `autoBallSemParar`). Volta ao modo `active` no próximo
  `rank.mode` `active` (semana nova ou nível novo com hunt nova).

O `rank` com `dry_run: false` confere na subida, pelo `store.plugin_configs`, se o `restock` está ligado com
`focus: "rank"`. Se não estiver, não age: grava `rank.plan` com `degraded: ["restock_focus"]` e continua só
gravando `rank.would`, como no ensaio (os dois brigariam pelo `auto.set`). O `focus.set` (seção 7) reinicia os
dois plugins, então a conferência sempre vê a config nova.

O `restock` assina `rank.mode`. Ao subir com `focus: "rank"`, lê o último `rank.mode` gravado (pelo
`recent_events` da última semana) para não esperar o `rank` replanejar.

### 5. `weekly_ball_budget` (D-G)

Fica **sem teto**: o campo não entra neste passo. Se precisar depois, a conta é `preço × tentativas` dos
`capture_attempt` da semana.

Para ter uma ideia: com a Great Ball (20 de ouro, 0,73% no Bellsprout) uma espécie do 1º estágio custa ~2,7 mil de
ouro; as 32 espécies da fila de hoje ficariam em ~100 mil.

### 6. Fila vazia

Quando a fila acaba, o `rank` grava `rank.plan` com `target: null`, publica `rank.mode` `fallback` e para de mandar
`auto.set`. Se `fallback_hunt` estiver definido e a conta não estiver nela, manda o `hunt.select` para lá (com as
mesmas regras de trava e confirmação). A partir daí quem cuida das bolas é o `restock`, no `fallback_focus`.

### 7. Painel: seletor de foco (D-I)

**Comando novo `focus.set`** no worker, para os dois plugins mudarem juntos:

```json
{"focus": "rank",
 "rank": {"rank_balls": [4, 3, 2, 1], "rank_ball_rule": "se_paga",
          "fallback_focus": "gold_xp_drop", "fallback_hunt": null}}
```

- `focus`: `"capture"`, `"gold_xp_drop"` ou `"rank"`.
- Preserva o resto da config do `restock` (`items`, `ball_min` etc.) e troca só `focus` e `fallback_focus`. Com
  `focus: "rank"`, o `fallback_focus` vem de `rank.fallback_focus`.
- Com `focus: "rank"`: `rank` ligado com a config atual mais os campos de `rank` e `dry_run: false`. Com os outros
  focos: `rank` desligado (a config fica guardada).
- Valida as duas configs antes de gravar qualquer uma (nada é gravado se uma for inválida), grava as duas e
  reinicia os dois plugins se a sessão estiver conectada.
- Resposta: `{"focus": ..., "applied": "agora" | "na próxima conexão"}`.

**Página da conta** (`/contas/<id>`): um card "Foco" acima dos plugins.

- Mostra o foco atual: `rank` se o `rank` está ligado com `dry_run: false` e o `restock` em `focus: "rank"`; senão,
  o `focus` do `restock` (sem `restock`, ouro-xp-drop, o padrão do app); "rank (ensaio)" se o `rank` está ligado em
  `dry_run`.
- Três opções (captura, ouro-xp-drop, rank). Com rank: bolas permitidas (checkboxes na ordem Ultra, Super, Great,
  Poke), regra (`se_paga`/`fixa`), foco de fallback (ouro-xp-drop/captura) e hunt de fallback (texto, vazio =
  fica onde está).
- "Salvar e aplicar" manda o `focus.set`. Os editores JSON continuam embaixo, para os outros campos.
- Sem framework de testes no web: confere-se com `npm run typecheck` e no navegador.

### 8. Config nova

`RankConfig`:

| Campo | Padrão | Uso |
|---|---|---|
| `dry_run` | `true` | continua o padrão; o `focus.set` grava `false` |
| `switch_margin_s` | `0.5` | folga depois da trava e do `trocaLivreEm` |
| `switch_confirm_s` | `15` | prazo para o `hunt.changed` |
| `switch_retry_s` | `60` | espera depois de uma troca que falhou |
| `max_switches_per_hour` | `10` | teto de `hunt.select` por hora |
| `retry_after_s` | `60` | espera pelo `estado` depois de um `auto.set` |
| `fallback_hunt` | `null` | hunt para quando acabar a fila; `null` = fica onde está |

`RestockConfig`: `focus` aceita `"rank"` e o padrão passa de `"capture"` para `"gold_xp_drop"` (o padrão do app,
D-H); `fallback_focus` (padrão `"gold_xp_drop"`). Contas com `restock` sem `focus` na config passam a ficar em
ouro-xp-drop; a conta de hoje vai receber o foco explícito pelo `focus.set`.

### 9. Como ligar na conta

1. No painel, foco **rank** com as bolas e o fallback padrão.
2. Acompanhar o primeiro `hunt.select`, o `hunt.changed` e o `auto.set` no log, e a primeira captura com
   `rank.catch` `scores: true`.

### Fora deste passo

- `ball.throw` (plano B, só se o Lançar até Capturar não servir).
- `weekly_ball_budget` (D-G).
- Métricas `rank_points`/`rank_species_week` e o card do rank no painel: passo 6.
- Medir o abates/h das hunts visitadas com menos de `min_active_minutes` (hoje só conta com 30 min; com ~8 min
  por hunt, quase nenhuma vai virar "medida"). Pode entrar no passo 6 se a fila ficar ruim.

## Decisões (tomadas em 15/11)

- **D-E. Intervalo do `HuntSelect`**: 20 s, com teto de 10 trocas por hora no plugin.
- **D-F. Dois donos do `auto.set`**: o `rank` só age com o `restock` em `focus: "rank"`.
- **D-G. `weekly_ball_budget`**: sem teto (sai deste passo).
- **D-H. Fallback**: o `restock` assume no `fallback_focus`, escolhido no painel; padrão `gold_xp_drop`, o padrão do
  app. A conta nunca fica parada. O padrão do `RestockConfig.focus` também passa a ser `gold_xp_drop`.
- **D-I. Seletor de foco no painel**: no passo 5, com os parâmetros do rank.
- **D-J. Bola fora do alvo**: não desliga. O `auto.set` sai junto com o `hunt.select` e é religado sempre que a
  flag cair com alvo definido.

## Casos de teste propostos

Em `worker/tests/test_rank_plugin.py` (o catálogo, o gateway falso e o relógio dos casos 1 a 21), com o gateway em
`enabled`, `dry_run: false` e o `restock` em `focus: "rank"`, salvo quando dito.

Trava e troca:

22. **Trava aberta**: `combat_free_at` e `switch_free_at` no passado → `hunt.select caterpie` sai na subida.
23. **Trava fechada**: `combat_free_at` 3 s no futuro → nada sai; um `kill` com o relógio 4 s depois → sai.
24. **`trocaLivreEm`**: `switch_free_at` 8 s no futuro → espera; depois sai.
25. **Relógio do servidor**: `server_offset` de +5 s e trava em `local + 3 s` → já pode (o servidor está em
    `local + 5 s`).
26. **Confirmação**: `hunt.changed caterpie` → hunt atual atualizada e o tempo no alvo começa.
27. **Erro do jogo**: `game.error` com `hunt.select` pendente → `rank.failed` com a chave; nova tentativa só depois
    de `switch_retry_s`.
28. **Sem confirmação**: 15 s sem `hunt.changed` → `rank.failed` `timeout`; na 3ª falha seguida →
    `switch_failed` e a espécie vai para `skipped`.
29. **Teto por hora**: 10 trocas na última hora → a 11ª espera; `rank.plan` `switch_cap` uma vez só; quando a
    primeira sai da janela, a troca sai.

Lançar até Capturar:

30. **Junto com a troca**: na subida, na Magikarp, com `autoBallSemParar: true` → `hunt.select caterpie` e
    `auto.set` com `autoBallAteCapturar: true`, `autoBallSemParar: false` e a bola na frente, sem esperar o
    `hunt.changed`.
31. **Captura do alvo**: `rank.catch {species_id: 10, scores: true}` e o `estado` com a flag em `false` →
    replaneja, `hunt.select metapod` e `auto.set` religando a flag.
32. **Religar**: com alvo, um `state.patch` com `autoBallAteCapturar: false` sem `rank.catch` que pontue →
    `auto.set` de novo.
33. **Sem repetição do `auto.set`**: 100 `kill` sem o `estado` refletir → um `auto.set` só em 60 s; aos 61 s,
    outro.

Dono do `auto.set` e fallback:

34. **`restock` em outro foco**: `restock` com `focus: "capture"` → `rank.plan` com `degraded: ["restock_focus"]`,
    `rank.would` em vez de ações.
35. **`rank.mode`**: na subida com alvo → `rank.mode` `active` com a bola; com tudo pontuado → `rank.mode`
    `fallback` `queue_empty`, sem `auto.set`; sem repetir o mesmo modo a cada plano.
36. **Fila vazia com `fallback_hunt`**: `fallback_hunt: "magikarp"`, conta na Caterpie → `hunt.select magikarp`;
    sem `fallback_hunt` → nenhum `hunt.select`.
37. **Volta do fallback**: em fallback, subiu de nível e entrou hunt nova na fila → `rank.mode` `active`,
    `hunt.select` e `auto.set`.
38. **`HuntSelect`**: `min_interval_s == 20`.

Em `worker/tests/test_restock.py`:

39. **Foco `rank`, modo `active`**: nunca manda `auto.set`; com `rank.mode {active, ball_id: 2}` e Great Ball
    abaixo do `ball_min` → compra Great Ball; poções como antes.
40. **Foco `rank` antes do primeiro `rank.mode`**: sem `rank.mode` gravado → age como `active` sem bola (não
    compra bola, não manda `auto.set`); com um `rank.mode` gravado → usa ele.
41. **Fallback `gold_xp_drop`**: `rank.mode` `fallback` → `auto.set` com as flags de bola em `false`, não compra
    bola.
42. **Fallback `capture`**: `fallback_focus: "capture"` e `rank.mode` `fallback` → escolhe a bola pelo ouro líquido
    e liga o `autoBallSemParar`, como no foco captura; `rank.mode` `active` depois → para de mandar `auto.set`.

47. **Padrão do foco**: `RestockConfig()` sem `focus` → `gold_xp_drop` (os testes atuais do foco captura passam
    a declarar `focus: "capture"`).

Em `worker/tests/test_commands.py`:

43. **`focus.set rank`**: `restock` com `items` → `restock` gravado com os mesmos `items`, `focus: "rank"` e o
    `fallback_focus`; `rank` ligado com `dry_run: false` e os campos enviados; os dois reiniciados.
44. **`focus.set gold_xp_drop`**: `restock` com `focus: "gold_xp_drop"`, `rank` desligado com a config preservada.
45. **Inválido**: `focus: "xyz"`, ou `rank_balls: []` → `CommandError` e nada gravado.

Em `worker/tests/test_session.py`:

46. **`AccountStateView`**: `state.patch` com `centro_livre_em` → `combat_free_at`; `hunt.changed` com
    `switch_free_at` → guardado; `server_now()` soma o `server_offset`.
