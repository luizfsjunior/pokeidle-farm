# Fase 3a: reposição automática de consumíveis

Status: **rascunho**. Faltam a captura do `shop.buy` no DevTools (seção 5) e as decisões da seção 6.
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
- `to_wire()`: `{t: "shop.buy", kind, id, qty}`. **A confirmar na seção 5.**
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
2. Comprar na loja do NPC **1 Poké Ball** e depois **1 Potion**.
3. Anotar as mensagens **enviadas** (seta para cima) e as **recebidas** logo depois (seta para baixo).
   Não precisa do `hello`, que tem o token.
4. Na loja, anotar o preço de cada poção e revive e o id, se aparecer.
5. Fechar a aba **sem "Sair"**.

## 6. Decisões em aberto

- **D1. Bola:** repor qual? A Ultra Ball (130, 1,2% em Magikarp) captura 4× mais que a Poké Ball (5, 0,3%),
  mas custa 26× mais. Em Magikarp, cada captura sai por ~10.800 de ouro com Ultra e ~1.700 com Poké.
  Como o "sem parar" joga uma bola por abate (~1.000 por hora), a **Ultra gasta ~130.000 de ouro por hora**
  e a hunt rende **~41.000**: com Ultra a conta perde ouro. A Poké gasta ~5.000 por hora.
- **D2. Limites:** mínimo, alvo, reserva de ouro e teto por hora (os números do exemplo são um chute).
- **D3. Poções e revives:** quais ids repor (200 a 204 e 205/206 são da automação nativa) e com quais limites.
- **D4. Ligar onde:** só na conta `luizfsjunior_1`, pelo `strategy_configs`?
- **D5. Tempos:** intervalo mínimo entre compras (sugestão: 10 s) e quanto esperar a confirmação (sugestão: 15 s).
