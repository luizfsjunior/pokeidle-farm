# Página Vendas (16/11/2026)

Mostra, no painel (`/vendas`), os anúncios das contas no Mercado: os abertos, os vendidos e os cancelados, e
também o que o worker fez. Não há tabela nova: tudo sai de `events` (`web/lib/sales.ts`).

## Fontes

| Evento | O que traz |
| --- | --- |
| `market.reply`, aba `meus` | a lista dos próprios anúncios (`linhas`), pedida pelo seller a cada ciclo |
| `market.reply`, aba `criado` | o anúncio recém-criado (`anuncio`) |
| `action.sent` / `action.blocked` / `action.failed` de `market.criar`, `market.cancelar` e `market.meus` | o que o worker mandou ou deixou de mandar |
| `seller.plan`, `seller.would`, `seller.failed`, `seller.probe` | os ciclos do seller e a simulação (`dry_run`) |
| `unknown` com `t` = `venda`, `marketComprado`, `aviso` ou `mktSorteio` | avisos do jogo, ainda sem formato mapeado; a página mostra os campos simples |

## Como cada anúncio é classificado

Os anúncios são agrupados pelo `id` do jogo.

- **Aberto:** está na última lista `meus` com `estado: "aberto"`.
- **Vendido:** o jogo marcou o anúncio com um `estado` de venda.
- **Saiu da lista:** o anúncio estava aberto numa lista `meus` e sumiu na seguinte, sem `market.cancelar` do
  worker. Quase sempre é venda, mas pode ter sido cancelado no navegador. Conta como vendido nos totais.
- **Cancelado:** o worker mandou `market.cancelar` para esse id.
- **Venda parcial:** a quantidade caiu com o anúncio ainda aberto; a diferença conta como vendida.

As gemas recebidas descontam a taxa de 15% do Mercado.

## Limites

- Só aparece o que passou pelo worker: anúncios criados no navegador entram quando o seller lê a lista `meus`.
- A seção "Diagnóstico" conta as respostas `market` por aba. Se a lista `meus` não aparecer, é ali que se vê com
  que nome ela chegou.
