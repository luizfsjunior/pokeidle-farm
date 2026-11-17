# Ficha do pokémon e Pokédex mais completa

Pedido de 17/11: clicar num pokémon da conta abre a ficha dele, como no jogo, e a Pokédex mostra mais da espécie.

## O que a ficha mostra

Ao clicar num pokémon da equipe, dos destaques ou dos shinies, a página da conta abre uma gaveta com:

- **Nota** de 0 a 10 e a faixa dela (Fraco, Mediano, Bom, Forte, Poderoso...), nas cores do jogo. Lendário e mítico
  aparecem como "Inestimável", como no jogo.
- **Potência**, **qualidade**, **IV** (soma de 192), **poder**, **HP** e o **XP do nível**.
- **Stats**: o base da espécie e o IV de cada stat (de 1 a 32).
- **Tipos**: as fraquezas (×2, ×4), as resistências, as imunidades, onde os tipos dele batem forte e onde batem fraco.
- **No PvP**: o alcance no tabuleiro (corpo a corpo ou 2, 3 ou 4 casas) e a conta que o define.
- **Evolução**, **golpes** (os já aprendidos no nível dele em destaque, os de TM à parte), raridade e captura.
- Os botões de equipe (tornar ativo, pôr na equipe, tirar).

A ficha da espécie na Pokédex ganha raridade, XP por derrota, quanto o NPC paga, tipos, stats base, alcance no PvP
e golpes.

## De onde vêm os números

- **Perfil** (`account_profile`): o worker agora guarda o `ivs` de cada pokémon, além de XP, apelido, refino, TMs,
  item segurado e quem capturou, quando o jogo manda (`profile.compact_pokemon`). A lista dos campos que os pokémons
  trazem fica em `extra.pokemon_keys`, para descobrir o que mais dá para mostrar.
- **Espécie** (`game_species.data`): stats base, golpes, XP por derrota e preço no NPC. A descrição do jogo hoje é só
  "a zubat", e a ficha não mostra essa.
- **Tabela de tipos**: `game_catalog.regras.tabelaTipos`, com a diagonal do `tipo-efetividade.mjs` (golpe do mesmo
  tipo do defensor).
- **Nota**: porte de `model/capture.py` (`pokemon_grade`) para `web/lib/pokemon.ts`; as duas dão o mesmo número.
  As faixas (`FAIXAS_NOTA`) e o piso por evolução (`GANHO_MIN_EVOLUCAO`) vêm do `shared/nota-pokemon.mjs`, que o
  worker passa a sincronizar em `game_files`. Até o arquivo chegar, a ficha mostra o número sem a faixa, e as formas
  evoluídas podem sair um pouco abaixo da nota do jogo.
- **Alcance no PvP** (`shared/pvp-tabuleiro.mjs`): folga = Sp. Atk − o maior entre Ataque e HP. Folga ≤ 0 dá corpo a
  corpo; de 1 a 24, 2 casas; de 25 a 49, 3; 50 ou mais, 4.

## Pokédex: por conta ou conjunta

A Pokédex do jogo é de cada conta, e o painel mostra a da conta escolhida. A aba **Todas** junta as contas, somando
capturas e abates por espécie. O worker grava o perfil a cada ~2 minutos, e a página busca de novo a cada minuto.
