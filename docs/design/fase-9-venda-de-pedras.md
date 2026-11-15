# Fase 9: venda das pedras no Mercado

Status: **implementado em ensaio** (15/11/2026): o plugin `seller` calcula e grava o que venderia (`seller.would`),
sem anunciar. Ligar de verdade com `{"dry_run": false}` depois de conferir os planos.

## Decisões (15/11)

- **Só pedras de evolução** por enquanto (outros itens depois).
- **Guardar 5 de cada pedra** (para evoluir; às vezes a espécie não está no time ou vai ser capturada depois).
- **Preço**: 1 gema abaixo do menor anúncio aberto dos outros vendedores, nunca abaixo do mínimo do Mercado (2 gemas,
  `ceil(1 / 0,85)`), e **nunca abaixo de 85% da média de 7 dias**: abaixo do piso, a pedra fica guardada (não se
  despeja estoque num mercado saturado).
- Sem nenhum anúncio de outros vendedores: anuncia pela média de 7 dias.

## O que o jogo mostrou (sonda de 15/11)

O worker anunciou 1 Water Stone a 999 gemas e cancelou (estoque 15 → 14 → 15). Protocolo em
[protocolo.md](../protocolo.md) (`market.item`, `market.criar`, `market.meus`, `market.cancelar`):

- `market.criar` responde `market` aba `criado` com o anúncio: `compravelEm` (+2 min, a retenção) e `editavelEm`
  (+30 min: só depois disso dá para mudar o preço). Item não expira. O item sai do inventário pelo `estado`.
- `market.cancelar` funciona a qualquer momento e devolve o item ao inventário.
- **O preço real é outro**: os 60 anúncios abertos de Water Stone (4.607 unidades) estavam todos a **2 gemas**, o
  mínimo, enquanto a "média de 7 dias" do `market.medias` dizia ~30. A média não é o preço de hoje.

Por isso, antes da venda:

1. **`market_asks`**: a cada snapshot de médias (de hora em hora), o `market_prices` lê os anúncios abertos de cada
   pedra (`market.item`, uma a cada 11 s) e grava o menor preço, as unidades nele, a fila e o número de anúncios,
   sem os da própria conta.
2. **Preço de venda realista** = o menor entre a média de 7 dias e o menor anúncio aberto (das últimas 6 h). Vale para
   o foco gemas (`StonePrice.sell`), para a métrica `drops_value_orb` (recalculada desde 12/11), para o `/compensa`,
   para `/hunts`, `/mercado` e o card de gemas.

## Ciclo do `seller` (a cada 30 min)

1. Lê os próprios anúncios (`market.meus`).
2. Para cada pedra do catálogo: total = inventário + já anunciado; quer vender total − 5.
3. Preço-alvo e piso como acima. Alvo abaixo do piso → `guarda_abaixo_do_piso`.
4. Sem anúncio próprio → anuncia o excesso. Anúncio próprio mais caro que o alvo (alguém passou na frente) → cancela e
   anuncia de novo no alvo. 5 ou mais unidades novas além do anunciado → anuncia um lote à parte. Até 20 anúncios.
5. Grava `seller.plan` com a decisão de cada pedra; em ensaio, `seller.would` com cada ação.

Config (`SellerConfig`): `dry_run` (true), `keep` (5), `floor_ratio` (0,85), `interval_min` (30), `min_lot` (5);
para diagnóstico, `probe_price`/`probe_item_id` (sonda) e `cancel_ids` (cancelar anúncios por id).

## Testes

`worker/tests/test_seller.py` (sonda, cancelamento, decisões do ciclo: guarda abaixo do piso, anuncia o excesso,
reprecifica, lote novo, limite, sem dry_run; resumo dos anúncios sem os próprios; preço realista) e o caso do anúncio
a 2 gemas em `supabase/tests/drops_value_test.sql`.

## Em aberto

- Equipar o melhor time para a hunt (`team.active`/`team.move` e a efetividade de tipos): próxima etapa.
- Outros itens além de pedras.
