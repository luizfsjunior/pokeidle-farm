# Fase 7: preços do Mercado e valor dos drops

Status: **rascunho**, 15/11/2026. Decisões D-O a D-S em aberto (fim do documento).

É a fase 7 do [roadmap](../roadmap.md): métricas derivadas do Mercado (valor dos drops) e objetivos sobre elas.
Ela alimenta o critério de "compensa?" da fase 8:

```
renda_mensal_usd = Σ(valor_em_gemas_dos_drops_vendidos × (1 − comissão)) × 0,009
```

Hoje o worker conta os drops (`drops` no `metric_hourly`), mas não sabe quanto eles valem.

## O que já sabemos (15/11, pelo `app.js` público v1.420.0 e pelos eventos gravados)

**Drops.** O `batalha` `k: morte` traz `drops: [{"qtd": 1, "nome": "Water Stone"}]`. O tradutor guarda só o nome
(`kill.data.drops = [{"name": ...}]`) e perde a quantidade; a métrica `drops` conta entradas, não unidades.

**Catálogo de itens.** `https://pokeidle.io/assets/items.json` (público, com `ETag`, como os `creatures*.json` da
Pokedex): `{"items": [{"id": 142, "name": "Water Stone", "icon": ..., "category": "stone", "rare": true,
"npcPrice": 5000}, ...]}`. O nome do drop casa com o `name`. Os itens próprios do servidor (ids ≥ 70000) vêm no
`welcome.itensNossos`.

**Médias do Mercado.** O cliente manda `{"t": "market.medias"}` (sem parâmetros) quando a mochila está aberta e
guarda a resposta por 5 min. A resposta é um `market` com `aba: "medias"`:

```json
{"t": "market", "aba": "medias", "dias": 7,
 "medias": {"142": {"orb": {"media": 12.5, "unidades": 340}, "gold": {"media": 4800, "unidades": 90}}}}
```

`media` = preço médio de venda em cada moeda (`orb` = gemas, `gold` = ouro) nos últimos `dias` dias, e
`unidades` = quantas unidades foram vendidas. Item sem venda na moeda: sem a chave. (Formato lido do código do
cliente: `estado.rmtMedias = {itens: m.medias, dias: m.dias}`, `m.media`, `m.unidades`; os números do exemplo são
inventados. **A confirmar com uma resposta real**, passo 1.)

Outras leituras do Mercado (`market.item`, `market.itens`, `market.listar`) trazem anúncios abertos, não preços
fechados; ficam para a fase 9 (sniper).

## Proposta

### 1. Confirmar a resposta (antes de tudo)

O worker manda um `market.medias` uma vez (ação de leitura, como o `topcatch.pedir`) e grava a resposta inteira
como `market.prices` com o `raw`. Confiro o formato e quantos itens vêm, e o `protocolo.md` registra.

### 2. Drops com quantidade

`Drop` ganha `qty` (do `qtd`, padrão 1). A métrica `drops` passa a somar `qty` (recalculada desde o início).

### 3. Catálogo de itens

Igual à Pokedex (`gamedata.py`): o worker baixa o `items.json` com `If-None-Match` na subida e grava numa tabela
nova `game_items (id, name, category, rare, npc_price, updated_at)` só quando muda. Os `itensNossos` do `welcome`
entram na mesma tabela.

### 4. Preços

- **Ação nova `MarketAverages`** (`market.medias`, só leitura, intervalo mínimo 5 min).
- **Plugin novo `market_prices`** (core, sobe sempre, mas só numa conta por worker para não repetir o pedido):
  pede a cada `interval_min` (padrão 60) e grava cada resposta.
- **Tradutor**: `market` `aba: "medias"` vira `market.prices` (`days`, `prices: {item_id: {orb, gold}}`).
- **Tabela `market_prices`** (`taken_at`, `item_id`, `currency`, `avg`, `units`, `days`): uma linha por item e moeda
  a cada pedido. Com ~1.000 itens e 24 pedidos por dia, ~50 mil linhas por dia; guarda 30 dias (D-R).

### 5. Métricas

Bases novas em `metric_hourly`, por hora e hunt, somadas no `refresh_metric_hourly`:

| `key` | Valor |
|---|---|
| `drop_units` | unidades dropadas (soma de `qty`) |
| `drops_value_orb` | Σ `qty` × média em gemas do item |
| `drops_value_gold` | Σ `qty` × média em ouro do item |

e as razões por hora ativa (`drops_value_orb_per_hour`, `drops_value_gold_per_hour`).

O preço de cada drop é o do **último `market_prices` antes do fim daquela hora** (D-P), para o histórico não mudar
quando os preços mudam. Item sem média na moeda: vale 0 (D-Q). Drop cujo nome não está no catálogo: vale 0 e entra
numa contagem `drops_unpriced`, para aparecer no painel.

### 6. Painel

- Visão geral: "Drops (gemas)/h" e "Drops (ouro)/h" no card de cada conta.
- `/metricas` já mostra qualquer métrica nova; objetivos do tipo `metric` funcionam sem mudança.
- Página nova `/mercado` (simples): tabela dos itens que a conta dropou nos últimos 7 dias, com unidades, preço médio
  em gemas e ouro, unidades vendidas no Mercado e o valor total.

## Fora desta fase

- Vender no Mercado (fase 9) e a comissão real de venda (a fase 8 usa a `taxaMercado` do `welcome.economia`).
- Preço de pokémon capturado (o valor depende de IV, shiny etc.; não há média simples).

## Decisões em aberto

- **D-O. Moeda**: valorar nas duas (gemas e ouro), com métricas separadas (proposta), ou só em gemas, que é o que
  entra no critério da fase 8?
- **D-P. Preço histórico ou atual**: o preço da hora do drop (proposta; o histórico fica estável), ou sempre o mais
  recente (o valor de tudo muda a cada pedido)?
- **D-Q. Item sem venda**: vale 0 (proposta) ou cai para o `npcPrice` em ouro? O `npcPrice` do `items.json` ainda
  não está claro se é o preço de compra ou de venda no NPC.
- **D-R. Frequência e retenção**: `market.medias` a cada 60 min e 30 dias de `market_prices`?
- **D-S. Página `/mercado`** nesta fase, ou só as métricas e o card?

## Casos de teste propostos

Worker:

1. Tradutor: `morte` com `drops: [{"qtd": 3, "nome": "Water Stone"}]` → `kill.data.drops == [{"name": "Water
   Stone", "qty": 3}]`; sem `qtd` → `qty: 1`.
2. Tradutor: `market` `aba: "medias"` → `market.prices` com `days` e `prices`; outras abas do `market` → nada novo.
3. `MarketAverages` → wire `{"t": "market.medias"}`, `min_interval_s == 300`.
4. `market_prices`: pede na subida e a cada `interval_min` (relógio controlado); com o rate limiter barrando, tenta de
   novo quando ele deixar; só uma conta por worker pede.
5. Catálogo de itens: `ETag` igual → não regrava; `ETag` novo → grava; `itensNossos` do `welcome` entram.

SQL (`supabase/tests/drops_value_test.sql`):

6. `drop_units` soma `qty` (dois drops de 3 e 1 → 4).
7. `drops_value_orb`: 3 Water Stone com média 12,5 → 37,5; preço tirado do último snapshot antes do fim da hora
   (um snapshot depois da hora não muda o valor).
8. Item sem média em ouro → `drops_value_gold` 0 para ele; nome fora do catálogo → `drops_unpriced` 1.
9. Retenção: `purge_market_prices()` apaga snapshots com mais de 30 dias.

Painel: `npm run typecheck`, build e conferência no navegador.
