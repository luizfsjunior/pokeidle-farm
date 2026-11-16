# Seller: vender só o que a fila deixa vender (16/11/2026)

## O que os números mostraram

A tabela "Decisão do seller" do `/vendas`, em 16/11:

| Pedra | Média do jogo | Mediana das vendas | Menor anúncio | Piso | Decisão |
| --- | --- | --- | --- | --- | --- |
| Rock Stone | 20 | 185 (3 vendas) | 2 | 158 | guarda |
| Water Stone | 30 | 142 (1 venda) | 2 | 26 | guarda |

O Mercado está lotado a 2 gemas, que é o mínimo. As poucas vendas de pedras no histórico global saem a
preços muito acima disso, e não dá para separar uma transferência de uma venda real. Para pedras, nem a média
nem a mediana descrevem o preço pelo qual a nossa venda acontece.

Comparar o alvo com um piso tirado da média também é a pergunta errada. A 2 gemas não dá para anunciar mais
barato que a fila, só entrar no fim dela. A pergunta certa é se o anúncio vende e em quanto tempo.

## Regra

Por pedra, antes do piso:

1. **Fila à frente**: as unidades no menor preço quando o alvo empata com ele. É sempre o caso no mínimo de 2,
   porque não dá para furar. Quando o alvo fica 1 abaixo do menor anúncio, a fila à frente é zero.
2. **Vendas por dia**: unidades vendidas na semana (`market.medias`) ÷ 7.
3. **Dias para vender** = (fila à frente + o lote novo) ÷ vendas por dia. Sem volume, é infinito.
4. Acima de `max_days` (padrão 3), a decisão é **`guarda_fila_longa`** e o seller não abre anúncio novo.
   Os anúncios que já estão abertos continuam.

O piso continua, mas só como trava contra vender barato demais quando alguém anuncia muito abaixo. A
referência dele passa a ser a **menor** entre a média do jogo e a mediana das vendas, porque as duas podem
estar infladas.

**Preço estabelecido.** Às vezes o menor preço tem mais de um dia de demanda parada nele (fila à frente ≥
vendas por dia) e a fila anda (dias para vender ≤ `max_days`). Nesse caso o menor preço **é** o preço do
mercado: o piso desce até ele (`floor_reason: "preco_estabelecido"`). Em 16/11 a Rock Stone tinha 306 na
fila a 2 e ~257 vendidas por dia, com média de 21. O piso só continua valendo contra um anúncio isolado
barato, por exemplo 1 unidade a 2 numa pedra que vende a 100.

O `seller.plan` grava `ahead`, `per_day` e `days_to_sell` de cada pedra, e o `/vendas` mostra esses números.

## Em aberto

- Vender ao NPC por ouro, quando a pedra encalha em gemas. Depende de quanto o ouro vale para a conta.
- A fila supõe que, no mesmo preço, vende primeiro quem anunciou antes. Ainda não foi confirmado no jogo.
