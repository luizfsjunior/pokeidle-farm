# Painel, fase 2: Pokédex interativa e gráficos de evolução (16/11/2026)

## Pokédex (`/pokedex`)

O catálogo do jogo (`game_species`, ~1.300 espécies, lido em duas páginas de 1.000) cruzado com a Pokédex
da conta (`account_profile.pokedex`).

- Cada espécie aparece num de três estados:
  - **capturada**: sprite colorido e "×N" capturas;
  - **vista sem captura**: sprite em cinza;
  - **faltando**: silhueta e "???".
- Filtros por estado, busca por nome ou número e filtro por tipo. Tudo no navegador, sem nova consulta.
- O detalhe da espécie mostra tipos, raridade, capturas, abates, a evolução (clicável nos dois sentidos) e as
  hunts em que ela é a espécie principal (`game_hunts`). No celular abre como gaveta embaixo.
- A fase 3 vai pôr ali o botão "ir para esta hunt".

## Gráficos de evolução (página da conta)

Pequenos múltiplos, um gráfico por medida, sem eixo duplo: nível, XP, ouro, gemas, espécies capturadas e
pokémons, até 90 dias de `account_profile_daily`.

- Uma série por gráfico, então não há legenda. O valor atual fica ao lado do título.
- A mira segue o ponteiro e as setas do teclado.
- A variação no período aparece embaixo, e "Ver valores" abre a tabela.
- As cores são as das moedas, validadas com o validador da skill dataviz (contraste ≥ 3:1 sobre o cartão).
  O dourado da linha é mais escuro que o da moeda (`--gold-line`) no tema claro.
