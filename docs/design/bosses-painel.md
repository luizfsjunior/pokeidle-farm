# Página Bosses no painel

Pedido de 17/11: um lugar para ver os stats dos bosses e montar a equipe para eles.

## O que mostra

- **Regiões**: uma aba por região com o nível que ela pede. Kanto pede 300, Johto 650; depois disso, 300 + 350 × degrau³
  (`nivelMinimoDoPar`). Abre na região mais alta que a conta já alcança.
- **Cada boss do trio**:
  - tipos, nível e o **prêmio de hoje**. O prêmio gira entre TM, fragmento de Mega e tickets à meia-noite de Brasília
    (`premioDoBossNoInstante`, rodízio a partir de 17/11/2026);
  - o hexágono dos stats base;
  - fraquezas e resistências;
  - golpes e chances de prêmio por vitória: TM 0,5% × (degrau + 1), fragmento de Mega 0,65% × (degrau + 1),
    fragmento de Mega shiny 0,5% × (degrau + 1).
- **Da sua conta**: os pokémons da equipe e os mais fortes, na ordem de quem já está no nível do boss, depois quem bate
  mais forte nele (o melhor dos tipos dele) e quem leva menos (o pior dos tipos do boss). Também mostra quantos dos 5
  já estão no nível. Clicar abre a ficha do pokémon.

## Fontes e limites

- Trios, níveis, rodízio e chances vêm de `shared/bosses-lendarios.mjs` (em `game_files`), copiados para
  `web/lib/bosses.ts`. Se o jogo mudar o arquivo, a cópia precisa acompanhar.
- O código não diz de que tipo são os golpes do boss (`GOLPES_PADRAO_LENDARIO` não tem tipo). O "leva ×" supõe que eles
  saem no tipo do boss, como a Investida dos pokémons. Os dois golpes padrão são especiais, então Sp. Def e HP seguram
  o dano.
- Os stats mostrados são os base da espécie. O boss na arena tem os stats do nível dele e o bônus de lendário.
