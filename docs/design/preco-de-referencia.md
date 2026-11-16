# Preço de referência: mediana das vendas reais (16/11/2026)

## Problema

A "média de 7 dias" do `market.medias` é a média por unidade de todas as vendas do item. Poucas vendas
caras a puxam para cima. Uma delas pode ser a transferência de gemas entre contas de um mesmo jogador, como
anunciar 1 pedra por 5.000 gemas e comprar com a outra conta. Em 16/11 a Water Stone tinha média de ~30, com
4.607 unidades anunciadas a 2 que ninguém comprava.

A média entrava em dois lugares:

- **Valor dos drops** (métricas, `/mercado`, `/compensa`): já usava o menor entre a média e o menor anúncio
  aberto. A inflação era parcialmente contida.
- **Piso do seller** (85% da média): aqui não havia proteção. Num item com demanda real, mas média inflada, o
  seller guardaria estoque que venderia.

## Decisão

Uma função `public.market_reference(p_days, p_outlier)` (migration `20261116030000`) lê as respostas
`market.historicoGlobal` que o `market_prices` já grava (5 páginas de 30 vendas a cada 6 h). Cada linha é
uma venda: `{id, em, tipo, bruto, moeda, descricao: "135× Bronze Boss Token", vendedor, comprador}`.

1. A mesma venda aparece em várias varreduras: conta uma vez, pelo `id`.
2. Preço por unidade = `bruto` ÷ a quantidade da descrição. Sem "N×" na descrição, a venda é de 1 unidade.
   Só entram vendas de itens.
3. Ficam fora as vendas em que uma das nossas contas compra ou vende (transferência ou venda nossa).
4. Ficam fora as vendas acima de 3× a mediana simples do item, ou abaixo de 1/3 dela.
5. **Referência = mediana ponderada por unidades** das vendas que sobram: o preço em que metade das unidades
   vendeu.

A função devolve também a média das mesmas vendas, a média bruta (que mostra a distorção) e quantas vendas
ficaram fora, por preço e por serem nossas.

Os nomes de vendedor e comprador não são gravados em lugar nenhum. A função só os compara com os nicks das
nossas contas.

## Onde passa a valer

- **Seller:** `reference: "median"` (padrão) com `min_sales: 3`. Com 3 ou mais vendas em 7 dias, o piso e o
  alvo sem anúncios usam a mediana. Com menos, usam a média do jogo, como antes. `reference: "avg"` volta à
  regra antiga. O `seller.plan` grava `median`, `sales`, `ref` e `ref_source` de cada pedra.
- **`/mercado`:** tem uma coluna "mediana das vendas". O valor em gemas usa a referência, limitada pelo menor
  anúncio aberto, e a média fica destacada quando passa do dobro da mediana.
- **`/vendas`:** tem uma tabela "Decisão do seller" com média, mediana, menor anúncio, alvo, piso e o motivo.

Ainda na média (próximo passo): as métricas `drops_value_orb` (`refresh_metric_hourly`), o `/compensa` e o
`gems_model` do plugin gems.

## Atualização (16/11, mais tarde)

Para pedras, a amostra do histórico global mostrou poucas vendas, todas bem acima do livro de ofertas: a
Rock Stone tinha mediana de 185 (3 vendas) com a fila a 2. O seller passou a usar a **menor** entre a média
do jogo e a mediana, e a decisão principal virou a liquidez ([seller-liquidez.md](seller-liquidez.md)).
