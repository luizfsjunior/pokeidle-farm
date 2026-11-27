# Preço justo de pokémon no Mercado (27/11/2026, épico B)

## Problema

O seller só vende pedras. Para vender pokémon (shiny, P4/P5, nota alta, nível alto) é preciso saber quanto cada um
vale em gemas. A média do jogo não serve: as vendas de pokémon variam muito (um Charizard nível 80 P1 vendeu de 5 a
1.286 gemas na mesma semana) e as transferências de gemas entre contas de um mesmo jogador puxam a média.

A base existe: cada venda de pokémon no `market.historicoGlobal` (que o `market_prices` varre a cada 6 h) traz a
ficha inteira. Em 27/11 havia 9.138 vendas guardadas (15 a 27/11), de 463 espécies, 650 delas shiny.

## Decisão

Migration `20261127100000_preco_justo_pokemon.sql`:

1. **`market_pokemon_sales`**: uma linha por venda (espécie, shiny, potência, nota, qualidade, nível, poder, IV,
   refino, TMs, preço bruto, moeda e se uma conta nossa comprou ou vendeu). Sem nomes de jogadores. Preenchida por
   um gatilho em `events` (insert de `market.reply` da aba `historicoGlobal`), então o worker não muda. A migration
   importa o que já está em `events`. Guardada 90 dias (pg_cron, 04:53 UTC). ~760 vendas/dia → ~70 mil linhas, uns
   10 MB.
2. **`pokemon_net_gems(bruto)`**: o que entra depois da comissão por faixa (13% até 500, 10% até 5.000, 7,5% acima).
3. **`pokemon_fair_price(espécie, shiny, potência, nota, nível, tm_aoe, tm_fisico)`**:
   - comparáveis: últimos 30 dias, sem as nossas, mesma espécie (a forma, como Mega ou "Furious", já é outra
     espécie), mesmo shiny, mesmo TM de área e físico, nível entre a metade e o dobro;
   - potência: a mesma, se houver 5 vendas; senão a faixa (1–3, 4, 5);
   - fora: acima de 3× ou abaixo de 1/3 da mediana simples (transferências);
   - peso de cada venda: recência × nota parecida, `exp(-dias/7) × exp(-|Δnota|/0,5)`. A nota parecida é o ajuste
     pela nota: uma ficha de nota alta fica perto das vendas de nota alta;
   - preços: percentis ponderados. **Rápido** = 25%, **justo** = 50%, **esperar** = 75%;
   - menos de 5 comparáveis: `confidence = 'low'`, "poucas referências". O número aparece só como pista, e nenhum
     veredito sai dele;
   - raridade: `top_pct` = % das vendas da espécie (mesmo shiny) com nota maior ou igual.
4. **`pokemon_price_verdict(preço, justo, confiança)`**: para quem compra. Até 60% do justo é excepcional, até 80%
   ótimo, até 95% bom, até 115% justo, acima disso caro.
5. **`pokemon_prices(conta)`**: o preço de cada pokémon da coleção (só espécies com alguma venda no período).
6. **`pokemon_listing_verdicts()`**: os anúncios da última varredura da vitrine (24 h) com preço justo, diferença
   e veredito. A varredura pega os mais caros e os shiny, então serve para conferir a régua, não para achar
   pechincha.

Valor de AoE e Z-Move: em vez de somar um valor à parte, um pokémon com TM só compara com vendas que também têm.
Ainda não há amostra para separar o valor do TM.

## No painel

- **Pokémons da conta**: selo 💎 com o preço justo na grade, coluna 💎 na tabela e ordem "Preço no Mercado".
  Sem referências suficientes, nada aparece.
- **Ficha**: seção "No Mercado" com os três preços, o líquido depois da comissão, quantas vendas entraram e a
  raridade. Com poucas referências, diz quantas vendas há.
- **Economia**: "Pokémon na vitrine" com o veredito de cada anúncio.

## Primeira leitura (27/11, dados reais)

Das contas, só os Charizard nível 535 e 627 (P2) passam de 90 gemas (justo 99, rápido 78). Os de nível 100–140
ficam entre 5 e 22 gemas, antes dos 100 mil Coins por dia de anúncio. Com 13% de comissão e o custo do anúncio,
pokémon comum não compensa vender: o que vale é shiny, P5 e nível alto.

## Próximos passos

- B5: lucro vendendo como está, evoluindo ou megaevoluindo (custo das pedras de `market_reference`).
- B6: "força por gema" e a tabela de itens (menor preço, média de 7 dias, estoque, teto).
- B7 (depois dos protegidos, C1): o seller anuncia pokémon pelo preço justo, nunca abaixo do rápido.
