# Estimativa da Outland (no lugar do potencial em pedras)

Status: **implementado** (17/11/2026; chances e tiers corrigidos pela wiki no mesmo dia).

## Por quê

O card "Gemas" da aba Estratégia e o `/compensa` mostravam o potencial em pedras de evolução: cada pedra pelo preço
médio (até ~30 gemas) e vendida na hora. No Mercado real todas as pedras estão a **2 gemas** (~1,7 líquida) com filas de
semanas (Water Stone: 4.600 unidades na fila, ~1.000 vendidas por semana). O número real é perto de zero. Antes do 150
não há gema de verdade; o dinheiro começa na Outland ([análise](../analise-progressao-e-mercado.md)). Decisão do usuário
(17/11): trocar pela estimativa da Outland.

## Cálculo (`worker/src/pokeidle_farm/outland_model.py`)

```
gemas/h(hunt, tier) = abates/h × Σ (chance × mult. do tier × mediana das vendas reais × 0,85)
```

- **Abates/h**: simulador de combate (camada 1) com o ativo no nível 150, evoluído pela cadeia até onde o 150 alcança
  (o foco XP busca as pedras no caminho, [foco-xp-pedra.md](foco-xp-pedra.md)), contra cada hunt de área `outland`.
- **Chances** (wiki do jogo, 17/11; ver [foco-outland.md](foco-outland.md)): Key, Shiny Stone e Bicycle Fragment 1 em 250 mil abates cada,
  e Bronze Boss Token 1 em 10 mil, todos multiplicados pelo tier da Outland. O tier é o maior liberado pelo nível do
  treinador (`outlandTiers`: ×1 até o 499, ×1,1 no 500, ×2 no 2.250); o card mostra a Outland 1 e "o seu tier".
- **Preço**: a mediana das vendas reais (`market_reference`), não a média nem o anúncio. Item sem venda não conta.
- **Sem shiny**: não há shiny nas hunts da Outland.

O `market_prices` grava `outland.potential` a cada leitura de preços (no lugar do antigo `gems.potential`):
`{trainer_level, goal_level, active_species_id, active_name, top_tier_mult, prices, hunts, options[]}` com
`options[] = {slug, name, level, kills_per_hour, gems_per_hour, gems_per_hour_top, drops_per_day}`.

## Painel

Card **Outland** na aba Estratégia (e no `/compensa`): quantos níveis faltam e a previsão de chegada (do plano do foco
XP, quando há), gemas/h e US$/dia na melhor hunt no tier 1 e no tier alto, a tabela das 5 melhores hunts e os preços
usados.

## A conferir

- Os nomes dos itens no Mercado (`Key Fragment`, `Shiny Stone Fragment`, `Bicycle Fragment`, `Bronze Boss Token`): o
  card mostra "sem venda" para o que não casar.
- O formato de `outlandTiers` e se o tier também muda o nível/HP do selvagem (hoje o cálculo usa o nível da hunt).
- O foco "Gemas" (plugin `gems` com `objective: "gems"`) continua com o modelo de pedras.
