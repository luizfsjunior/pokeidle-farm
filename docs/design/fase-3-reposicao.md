# Fase 3a: reposição automática de consumíveis

Status: **implementado e ligado** na conta `luizfsjunior_1` em 13/11/2026 (`ACTION_MODE=enabled`). Primeira
rodada: escolheu a Great Ball em Magikarp, fez o `auto.set` e comprou 1.000 Great Balls; os dois confirmados
pelo `estado`. `shop.buy` e `auto.set` foram
confirmados no DevTools (ver [protocolo.md](../protocolo.md)) e os preços vieram dos prints da loja
(`worker/src/pokeidle_farm/catalog.py`). Testes: `worker/tests/test_restock.py`, os `test_*` da fase 3a em
`worker/tests/test_protocol.py` e `supabase/tests/ouro_liquido_test.sql`.

## Como ligar

1. Aplicar a migration `supabase/migrations/20261113000000_ouro_liquido.sql` no SQL Editor.
2. Ligar o plugin na conta (o `config` pode ficar `{}` para usar os padrões da seção 7):
   ```sql
   insert into public.strategy_configs (account_id, plugin, enabled, config)
   select id, 'restock', true, '{"items": [{"id": 205, "min": 10, "target": 30}]}'
     from public.accounts where nick = '<nick>';
   ```
3. Com `ACTION_MODE=observe_only` o plugin só registra o que faria (`action.blocked` e `restock.failed` com
   `reason: observe_only`). Para agir de verdade: `ACTION_MODE=enabled` no `.env` e `docker compose up -d`.
Depois disso vêm os casos de teste e só então a implementação.

## Objetivo

Repor **bolas, poções e revives** sozinho, comprando na loja do NPC com ouro, para a hunt não parar.
Motivo: em 12/11/2026 as bolas acabaram e o jogo parou de jogar sem avisar (ver [protocolo.md](../protocolo.md)).

É a **primeira vez que o worker age no jogo** (sai do `observe_only`). Por isso o escopo é estreito:
só compra na loja do NPC, com teto de gasto, uma compra por vez e tudo registrado.

## 1. O que o worker já sabe

| Dado | De onde vem |
|---|---|
| Estoque de bolas | `estado.balls` (`{"1": 0, "4": 27}`), no `welcome` e a cada arremesso |
| Estoque de poções e revives | `estado.items` (`{"200": 100, "205": 20}`), no `welcome` e em patches |
| Quais itens a automação nativa usa | `estado.automation.ballIds`, `potionIds`, `reviveIds` |
| Saldo de ouro | `estado.gold`, a cada abate |
| Preço das bolas | `catalogoBolas[].priceGold` no `welcome` (Poké 5, Great 20, Super 50, Ultra 130) |
| Preço de poções e revives | **não está no `welcome`** (só o da Golden Potion, 70070, em `itensNossos`). Ver seção 5 |

## 2. Peças

### Estado da conta

`AccountStateView` ganha `balls`, `gold` e `automation`, e `items` passa a ser atualizado pelos patches
(hoje só o `welcome` preenche). A sessão atualiza a partir de `state.snapshot` e `state.patch`.

### Ação `ShopBuy`

Primeira `ActionSpec` concreta, em `actions.py`:

- Entrada: `kind` (`"ball"` ou `"item"`), `id` e `qty`.
- `to_wire()`: `{t: "shop.buy", kind, id, qty}` (confirmado no DevTools).
- `min_interval_s`: a definir (D5).

### Plugin `restock`

Ligado por conta em `strategy_configs` (não é `always_on`). Ele escuta `state.snapshot` e `state.patch` e,
para cada regra da config:

1. Se o estoque do item está **abaixo do mínimo**, calcula quanto falta para chegar no **alvo**.
2. Se o ouro depois da compra fica **acima da reserva** e o gasto da última hora **não passa do teto**,
   manda **uma** `ShopBuy`.
3. Espera a confirmação (`k: "compra"`, ou o estoque subir no `estado`) antes da próxima compra.
   Sem confirmação em X s, desiste dessa compra e registra a falha (D5).

Regras do protocolo que ele respeita: uma compra por vez, o `RateLimiter`, e nada durante a trava de combate,
se a loja exigir (a confirmar).

Config (exemplo):

```json
{
  "rules": [
    { "kind": "ball", "id": 4,   "min": 50, "target": 300 },
    { "kind": "item", "id": 200, "min": 20, "target": 100 },
    { "kind": "item", "id": 205, "min": 5,  "target": 20 }
  ],
  "gold_reserve": 5000,
  "max_gold_per_hour": 50000
}
```

### Eventos

- `action.sent` e `action.blocked` (já existem no gateway).
- Novo `restock.bought` (`kind`, `id`, `qty`, `gold_spent`) e `restock.failed` (`kind`, `id`, `reason`), gravados,
  para auditoria e para uma métrica de gasto com consumíveis.

### `ACTION_MODE`

Hoje é global no `.env`. Para ligar a reposição, `ACTION_MODE=enabled`. Nada além do `restock` manda ações,
então o efeito real é só esse plugin.

## 3. Fora do escopo

- Escolher a bola por hunt (ex.: Poké em Magikarp, Ultra em hunt rara). Por enquanto, uma regra por item.
- Comprar no Mercado ou com Gemas.
- Vender pokémons ou itens.
- Mexer na `automation` do jogo (`auto.set`). A automação nativa continua sendo configurada no navegador.

## 4. Riscos

- **Mandar algo malformado ao servidor.** Mitigação: confirmar o formato no DevTools antes (seção 5) e ter
  um teste do `to_wire()` com o frame real.
- **Gastar ouro demais por bug** (ex.: comprar em loop). Mitigação: uma compra por vez esperando a confirmação,
  teto por hora, reserva mínima e o `RateLimiter`. Em caso de dúvida, o plugin para e registra `restock.failed`.

## 5. Captura no DevTools (precisa ser feita no navegador)

Com o worker parado (`docker compose stop`):

1. Abrir pokeidle.io/app → F12 → **Network** → filtro **WS** → clicar na conexão → aba **Messages**.
2. Comprar na loja do NPC **1 Poké Ball** e depois **1 Potion**. Depois, mudar **uma opção qualquer da
   automação** (para pegar o `auto.set`) e voltar ela como estava.
3. Anotar as mensagens **enviadas** (seta para cima) e as **recebidas** logo depois (seta para baixo).
   Não precisa do `hello`, que tem o token.
4. Na loja, anotar o preço de cada poção e revive e o id, se aparecer.
5. Fechar a aba **sem "Sair"**.

## 6. Decisões

### Tomadas em 12/11/2026

- **Foco por conta.** Cada conta tem um foco, e ele decide o que fazer com as bolas:
  - **captura**: usa a **melhor bola que não dá prejuízo** (regra abaixo);
  - **ouro-xp-drop**: não usa bola;
  - **rank semanal**: captura um de cada espécie e passa para a próxima, para subir no ranking semanal de
    espécies diferentes (o `topCatch`). Exige trocar de hunt sozinho (`hunt.select`) e entender o `topCatch`,
    então fica para uma **fase própria (3b)**. Nesta entrega só os dois primeiros focos.
- **Regra da bola (foco captura):** a bola de maior `catchRate` cujo preço é **≤ 100% do ouro médio por abate**
  (empate, sem margem). Em Magikarp (41 por abate) → Great Ball (20). Como o "sem parar" joga uma bola por
  abate, isso garante que as bolas não consomem mais ouro do que a hunt rende.
- **Duas métricas de ouro, porque cada uma conta uma coisa:**
  - **ouro médio por abate (bruto)**: o `ouro` das `morte`;
  - **ouro líquido**: o bruto menos o custo dos consumíveis gastos (bolas, poções, revives).
- **Trocar a bola é com o worker, via `auto.set`.** O jogo usa a primeira bola da lista `automation.ballIds`
  que tem estoque. O worker reescreve essa lista com a bola escolhida, partindo sempre do objeto
  `automation` atual. É a segunda ação nova desta entrega, e a mais delicada.

- **D1b. A regra usa o ouro líquido.** Como a própria bola é um consumível, a comparação é
  `preço da bola ≤ ouro bruto por abate − poções e revives por abate`. É a condição de o líquido, já contando
  a bola, ficar ≥ 0 ("não perder ouro" ao pé da letra).
- **D1c. No foco ouro-xp-drop o worker desliga a bola:** `autoBallSemParar` e `autoBallAteCapturar` em `false`,
  via `auto.set`.
- **D1d. Média em janela móvel:** os **últimos 200 abates da hunt atual** (~10 min em Magikarp), zerada quando a
  hunt muda. Diferente da "média até reset" do jogo, ela acompanha mudanças de rendimento (VIP, boost) em minutos.
  Fica **só na memória** do plugin, calculada dos `kill` e `capture_attempt` que já passam por ele; nada novo é
  gravado. Com **menos de 50 abates** na janela (hunt nova ou worker reiniciado), o worker **não mexe na bola**.

### Escolhas de implementação (sem pedido explícito, todas na config)

- **Foco captura** liga o `autoBallSemParar` (e desliga o `autoBallAteCapturar`) e põe a bola escolhida no
  começo da `ballIds`, mantendo as outras na ordem. Se **nenhuma bola se paga**, desliga a bola.
- O `auto.set` não é repetido por `retry_after_s` (60 s) enquanto o servidor não devolve a `automation` nova.
  Confirmado em 13/11/2026: o servidor devolve a `automation` no `estado`, então o `auto.set` sai uma vez só.
- A regra supõe uma bola por abate, e isso foi confirmado: o "sem parar" joga exatamente uma bola por selvagem
  abatido (cruzando os `slot`s).
- A confirmação da compra é o estoque subir no `estado`. Sem isso em `confirm_timeout_s`, `restock.failed`
  com `reason: timeout`. A compra segue observada por `late_confirm_s`: se o estoque subir nesse tempo, sai
  `restock.bought` com `late: true` e o gasto entra no teto. O mesmo item não é recomprado nesse meio-tempo.
- O teto por hora sobrevive a reinícios: ao subir, o plugin lê os `restock.bought` da última hora em `events`.
  Se a leitura falhar, ele segue com o teto zerado e avisa no log.
- Uma falha (`sem_ouro`, `observe_only`, `timeout`) é registrada uma vez e a regra espera `retry_after_s`
  antes de tentar de novo, para não gerar uma enxurrada de eventos.
- `item.consumed` sai do tradutor quando o estoque de um item da loja **cai** (compra só faz subir).

### Métricas de ouro no painel

O ouro bruto já existe (`gold` em `metric_hourly`). Para o líquido, o custo dos consumíveis precisa virar dado:

- O tradutor já conhece os preços das bolas (`catalogoBolas` do `welcome`) e passa a gravar `ball_price` no
  `capture_attempt`.
- Poções e revives: um evento `item.consumed` (`item_id`, `qty`, `unit_price`) quando o estoque de
  `estado.items` cai sem ter sido compra. Os preços vêm da captura do DevTools (seção 5).
- Novas métricas: `consumables_gold` (soma dos custos) e `gold_net` (`gold − consumables_gold`), por hora e
  por hunt, como as outras.

- **D1 (contexto da decisão acima). Bola:** repor qual? A Ultra Ball (130, 1,2% em Magikarp) captura 4× mais que a Poké Ball (5, 0,3%),
  mas custa 26× mais. Em Magikarp, cada captura sai por ~10.800 de ouro com Ultra e ~1.700 com Poké.
  Como o "sem parar" joga uma bola por abate (~1.000 por hora), a **Ultra gasta ~130.000 de ouro por hora**
  e a hunt rende **~41.000**: com Ultra a conta perde ouro. A Poké gasta ~5.000 por hora.
- **D2. Limites:** mínimo, alvo, reserva de ouro e teto por hora (os números do exemplo são um chute).
- **D3. Poções e revives:** quais ids repor (200 a 204 e 205/206 são da automação nativa) e com quais limites.
- **D4. Ligar onde:** só na conta `luizfsjunior_1`, pelo `strategy_configs`?
- **D5. Tempos:** intervalo mínimo entre compras (sugestão: 10 s) e quanto esperar a confirmação (sugestão: 15 s).

## 7. Config do plugin `restock`

| Campo | Padrão | O que faz |
|---|---|---|
| `focus` | `"capture"` | `"capture"` ou `"gold_xp_drop"` |
| `items` | `[]` | regras de poções e revives: `{"id", "min", "target"}` |
| `ball_min` / `ball_target` | 100 / 1.000 | estoque da bola escolhida |
| `gold_reserve` | 5.000 | ouro que nunca é gasto |
| `max_gold_per_hour` | 50.000 | teto de gasto em compras por hora |
| `window_kills` / `min_kills` | 200 / 50 | janela da média de ouro e mínimo para agir sobre a bola |
| `confirm_timeout_s` | 15 | espera pela confirmação da compra |
| `late_confirm_s` | 300 | quanto tempo uma compra que passou do prazo ainda pode confirmar (e bloqueia recompra do item) |
| `retry_after_s` | 60 | espera depois de uma falha ou de um `auto.set` |
