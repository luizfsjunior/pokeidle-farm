# Fase 3b: plugin `rank` agindo de verdade (passo 5)

Status: **rascunho**, 15/11/2026. Decisões D-E a D-J em aberto (fim do documento).

É o passo 5 da [ordem de implementação da 3b](fase-3b-rank-semanal.md#8-ordem-de-implementação). O passo 4
([plugin em ensaio](fase-3b-plugin-rank.md)) já decide a hunt alvo e grava o que faria. Aqui ele passa a mandar
`hunt.select` e `auto.set` de verdade, com `dry_run: false`.

O texto original do passo 5 era "`ball.throw` ligado, depois `hunt.select`". O `ball.throw` saiu: o Lançar até
Capturar do jogo (confirmado em 14/11) faz o papel dele. Numa hunt de uma espécie, ele joga bola até a primeira
captura e desliga sozinho, então o plugin só precisa trocar de hunt e religar a flag. O `ball.throw` continua como
plano B (seção 3.3 do desenho da 3b).

## O que muda em relação ao ensaio

1. **Trava de combate e `trocaLivreEm`.** O `hunt.select` só sai quando o relógio do servidor passa da trava
   (`centroLivreEm`) e do `trocaLivreEm` da última troca.
2. **Confirmação da troca.** O `hunt.select` só conta como feito quando chega o `hunt.changed` com o slug pedido.
   Sem isso, ou com `erro` do jogo, tenta de novo com espera.
3. **Ordem das ações.** O `auto.set` com o Lançar até Capturar só sai **depois** de chegar na hunt alvo. Ligado
   antes, ele gastaria a captura numa espécie que já pontuou (ex.: Magikarp hoje).
4. **Religar depois da captura.** O servidor desliga a flag na captura; o plugin religa na próxima hunt.
5. **Dono do `auto.set`.** Com o foco `rank`, o `restock` não mexe nas flags de bola, só repõe o estoque da bola
   que o `rank` escolheu.
6. **Fila vazia ou orçamento estourado**: `fallback`.

## Proposta

### 1. Trava e relógio do servidor

Medido em 15/11 (12 `state.patch` com `centroLivreEm`, conta nível 16 no Magikarp): a trava fica de 2,4 s a 5 s à
frente do relógio do servidor depois de cada golpe recebido. Ou seja, abre entre um golpe e outro, sem precisar
ir ao Centro.

- O `AccountStateView` ganha `combat_free_at` (o `centro_livre_em` do patch, em ms do servidor, convertido para
  `datetime` UTC) e `switch_free_at` (do último `hunt.changed`), mais `server_offset` (servidor − local, que o
  tradutor já calcula pelo `servidorAgora`). Fica também um método `server_now()`.
- O plugin só manda o `HuntSelect` quando `server_now() ≥ max(combat_free_at, switch_free_at) + switch_margin_s`
  (padrão 0,5 s). Se ainda não pode, guarda o pedido e confere de novo a cada evento (`kill`, `state.patch`,
  `field.tick` não: é ruído demais). Sem `server_offset` conhecido, usa o relógio local.

### 2. Confirmação, erro e nova tentativa

- Depois de mandar, espera o `hunt.changed` com o slug pedido por até `switch_confirm_s` (padrão 15 s).
- Chegou: a hunt atual vira o alvo, começa a contar o tempo no alvo e segue para o `auto.set` (seção 3).
- Chegou `game.error` nesse intervalo, ou o prazo passou sem confirmação: registra `rank.failed`
  `{action: "hunt.select", slug, reason: "<chave do erro>" | "timeout"}` e tenta de novo depois de
  `switch_retry_s` (padrão 60 s). Na 3ª falha seguida para o mesmo alvo, a espécie vai para `skipped` (como no
  timeout) e o plugin replaneja com `reason: "switch_failed"`.
- O `game.error` que chegar com um `hunt.select` pendente é o primeiro registro que teremos do erro de trocar na
  trava; a chave entra no `protocolo.md` quando aparecer.

**Intervalo do `HuntSelect`** (D-E): hoje o `min_interval_s` é 300 s. Com Bellsprout a ~8 min por captura e as
primeiras hunts da fila parecidas, 5 min entre trocas atrasa pouco, mas uma tentativa que falha prende o rate
limiter por 5 min. Proposta: `min_interval_s = 20` (cobre o `trocaLivreEm` de 10 s com folga) e um teto no
plugin, `max_switches_per_hour` (padrão 10), contado numa janela móvel. Estourou o teto: espera, com `rank.plan`
`reason: "switch_cap"` uma vez.

### 3. Lançar até Capturar

O `auto.set` desejado é o mesmo do ensaio (`ballIds` com a bola escolhida na frente, `autoBallAteCapturar: true`,
`autoBallSemParar: false`, o resto da `automation` atual), mas:

- **Só na hunt alvo**: se a hunt atual não é o alvo (indo para lá, ou fila vazia), o desejado é com as duas flags
  de bola em `false`. Assim a conta não captura nada fora da fila enquanto espera a trava.
- **Religar**: quando o `estado` traz `autoBallAteCapturar: false` (o `auto.catch_until_capture_off`) e a conta
  continua no alvo sem pontuar (captura de uma espécie que já tinha pontuado, ou a pontuação ainda não chegou),
  manda o `auto.set` de novo. O dedup do ensaio (`_sent`) passa a ser como o do `restock`: não repete o mesmo
  `auto.set` enquanto espera o `estado` refletir, por até `retry_after_s` (padrão 60 s), e manda de novo se a
  `automation` observada voltar a ser diferente da desejada.
- A captura do alvo chega como `rank.catch` com `scores: true`: replaneja (`captured`), o alvo novo sai na fila
  para o `hunt.select` e o `auto.set` só vem depois do `hunt.changed`.

### 4. `restock` com foco `rank`

`RestockConfig.focus` ganha `"rank"`:

- Nunca manda `auto.set`.
- Repõe as poções e revives como hoje.
- Repõe a bola que está em `automation.ballIds[0]` quando `autoBallAteCapturar` está `true` (a que o `rank`
  escolheu), com o `ball_min`/`ball_target` de sempre. Com a flag em `false`, não compra bola. Assim o `restock`
  não precisa saber da config do `rank`.

O `rank` com `dry_run: false` confere na subida, pelo `store.plugin_configs`, se o `restock` está ligado com
`focus: "rank"`. Se estiver com outro foco, não age: grava `rank.plan` com `degraded: ["restock_focus"]` e
continua só gravando `rank.would`, como no ensaio (os dois brigariam pelo `auto.set`). Um `plugin.set` no
`restock` reinicia só ele, então o `rank` relê isso quando o `restock` sobe de novo (D-F).

### 5. `weekly_ball_budget`

Ouro gasto em bolas na semana: a soma de `preço da bola × arremessos` dos `capture_attempt` desde o `week_start`
(lida na subida por uma função nova no banco, `rank_week_ball_spend(p_account, p_since)`, e somada a cada
`capture_attempt` depois). Passou do orçamento: vai para o `fallback` até a semana virar, com
`rank.plan` `reason: "budget"`. `null` = sem teto. Valor padrão em aberto (D-G).

Para ter uma ideia: com a Great Ball (20 de ouro, 0,73% no Bellsprout) uma espécie do 1º estágio custa ~2,7 mil de
ouro; as 32 espécies da fila de hoje ficariam em ~100 mil.

### 6. `fallback`

Quando a fila acaba (ou o orçamento estoura), o plugin não tem mais alvo. Proposta (D-H):

| Campo | Padrão | Uso |
|---|---|---|
| `fallback_hunt` | `null` | slug da hunt para onde ir; `null` = fica onde está |

Nos dois casos, o `rank` manda o `auto.set` com as duas flags de bola em `false` e para de agir até a semana virar
(ou subir de nível e aparecer hunt nova). A bola automática do foco captura fica de fora: ela é do `restock`, e o
foco do `restock` não muda sozinho.

### 7. Config nova (`RankConfig`)

| Campo | Padrão | Uso |
|---|---|---|
| `dry_run` | `true` | continua o padrão; o passo 5 liga com `false` na conta |
| `switch_margin_s` | `0.5` | folga depois da trava e do `trocaLivreEm` |
| `switch_confirm_s` | `15` | prazo para o `hunt.changed` |
| `switch_retry_s` | `60` | espera depois de uma troca que falhou |
| `max_switches_per_hour` | `10` | teto de `hunt.select` por hora |
| `retry_after_s` | `60` | espera pelo `estado` depois de um `auto.set` |
| `weekly_ball_budget` | em aberto | teto de ouro em bolas por semana; `null` = sem teto |
| `fallback_hunt` | `null` | hunt para quando acabar a fila |

### 8. Painel

O seletor de foco na página da conta (desenho da 3b, seção 7) fica para o passo 6, junto com o card do rank
(D-I). Até lá, liga-se pelo editor de plugins que já existe: `restock` com `focus: "rank"` e `rank` com
`dry_run: false`.

### 9. Como ligar na conta

1. `restock` → `{"focus": "rank", "items": [...]}` (os itens de hoje).
2. `rank` → `{"dry_run": false}`.
3. Acompanhar o primeiro `hunt.select`, o `hunt.changed` e o `auto.set` no log, e a primeira captura com
   `rank.catch` `scores: true`.

### Fora deste passo

- `ball.throw` (plano B, só se o Lançar até Capturar não servir).
- Métricas `rank_points`/`rank_species_week`, card e seletor de foco no painel: passo 6.
- Medir o abates/h das hunts visitadas com menos de `min_active_minutes` (hoje só conta com 30 min; com ~8 min
  por hunt, quase nenhuma vai virar "medida"). Pode entrar no passo 6 se a fila ficar ruim.

## Decisões em aberto

- **D-E. Intervalo do `HuntSelect`**: baixar de 300 s para 20 s, com teto de 10 trocas por hora no plugin?
- **D-F. Trava contra dois donos do `auto.set`**: o `rank` só age com o `restock` em `focus: "rank"` (proposta)
  ou age sempre e confia na config?
- **D-G. `weekly_ball_budget` padrão**: `null` (sem teto), ou um valor (ex.: 150 mil de ouro)?
- **D-H. `fallback`**: só `fallback_hunt` (proposta), ou também trocar o foco do `restock` para captura ou
  ouro-xp-drop quando a fila acabar?
- **D-I. Seletor de foco no painel** no passo 6 (proposta) ou já no passo 5?
- **D-J. Desligar a bola fora do alvo**: enquanto espera a trava ou sem alvo, as duas flags de bola em `false`
  (proposta). Custa alguns segundos sem bola, mas evita gastar a captura numa espécie que já pontuou.

## Casos de teste propostos

Em `worker/tests/test_rank_plugin.py` (o catálogo, o gateway falso e o relógio dos casos 1 a 21), com o gateway em
`enabled`, `dry_run: false` e o `restock` em `focus: "rank"`, salvo quando dito.

Trava e troca:

22. **Trava aberta**: `combat_free_at` e `switch_free_at` no passado → `hunt.select caterpie` sai na subida.
23. **Trava fechada**: `combat_free_at` 3 s no futuro → nada sai; um `kill` com o relógio do servidor 4 s depois →
    sai.
24. **`trocaLivreEm`**: `switch_free_at` 8 s no futuro → espera; depois sai.
25. **Relógio do servidor**: `server_offset` de +5 s e trava em `local + 3 s` → já pode (servidor está em
    `local + 5 s`).
26. **Confirmação**: `hunt.changed caterpie` → hunt atual atualizada, tempo no alvo começa, `auto.set` com
    `autoBallAteCapturar: true` sai.
27. **Erro do jogo**: `game.error` com `hunt.select` pendente → `rank.failed` com a chave; nova tentativa só depois
    de `switch_retry_s`.
28. **Sem confirmação**: 15 s sem `hunt.changed` → `rank.failed` `timeout`; na 3ª falha seguida →
    `switch_failed` e a espécie vai para `skipped`.
29. **Teto por hora**: 10 trocas na última hora → a 11ª espera; `rank.plan` `switch_cap` uma vez só.

Lançar até Capturar:

30. **Fora do alvo**: na subida, na Magikarp, com a `automation` em `autoBallSemParar: true` → `auto.set` com as
    duas flags em `false` antes do `hunt.select`.
31. **Captura do alvo**: `rank.catch {species_id: 10, scores: true}` → replaneja, `hunt.select metapod`, e o
    `auto.set` com a flag ligada só depois do `hunt.changed metapod`.
32. **Religar**: no alvo, `auto.catch_until_capture_off` sem `rank.catch` que pontue → `auto.set` de novo com a
    flag ligada.
33. **Sem repetição do `auto.set`**: 100 `kill` sem o `estado` refletir → um `auto.set` só em 60 s; aos 61 s,
    outro.

Dono do `auto.set`, orçamento e fallback:

34. **`restock` em outro foco**: `restock` com `focus: "capture"` → `rank.plan` com `degraded: ["restock_focus"]`,
    `rank.would` em vez de ações.
35. **`restock` em `focus: "rank"`**: não manda `auto.set`; com `ballIds[0] = 2` e `autoBallAteCapturar: true` e
    Great Ball abaixo do `ball_min` → compra Great Ball; com a flag em `false` → não compra bola; poções como
    antes.
36. **Orçamento**: `weekly_ball_budget` 1.000, gasto lido na subida de 900 e 6 `capture_attempt` de Great Ball
    (20) → no 5º passa do teto: `rank.plan` `budget`, `auto.set` com as flags em `false`, sem `hunt.select`.
    Virada da semana → volta a agir.
37. **Fila vazia com `fallback_hunt`**: todas as espécies pontuadas, `fallback_hunt: "magikarp"` → `rank.plan`
    com `target: null`, `hunt.select magikarp`, flags de bola em `false`. Sem `fallback_hunt` → fica onde está.
38. **`HuntSelect`**: `min_interval_s == 20` (se D-E for aceita).

Banco:

39. **`rank_week_ball_spend` no Postgres local**: soma `preço × tentativas` dos `capture_attempt` da conta desde
    `p_since`, por `ball_id`, com os preços do `game_catalog` (ou da tabela fixa, se a bola não estiver lá).
