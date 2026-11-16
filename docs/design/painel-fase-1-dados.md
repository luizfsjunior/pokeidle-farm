# Painel, fase 1: dados novos e histórico diário (16/11/2026)

Esta fase abre o caminho para a Pokédex interativa, os gráficos de evolução e os cards novos do painel
(docs/design/painel-perfil.md).

- **`account_profile.extra`**: campos do estado guardados como o jogo manda (`profile.EXTRA_KEYS`):
  `passe`, `ginasios`, `ginasiosPodio`, `guild`, `caixas`, `chocadeira`, `boss`, `outlandTier`, `casa`,
  `bicicleta`, `campConquistas`, `topMes`, `evento`, `pvp`, `automation`... Guarda também um recorte da
  `loja` (`vip`, `vipAte`, `looktype`, `gender`, `visual`). Um campo maior que 20 KB em JSON fica de fora.
  Assim o painel pode mostrar um campo novo sem mudança no worker, depois de ver o formato com
  `select extra from account_profile`.
- **`account_profile.pokedex`**: a Pokédex inteira (`{speciesId: {c, k, ...}}`, já com os `dexMud`).
- **`account_profile_daily`**: uma linha por conta e dia (fuso de Brasília), com nível, XP, ouro, gemas,
  diamantes, coleção e Pokédex. Uma trigger em `account_profile` grava a cada atualização e a última do dia
  fica. O worker não muda. O RLS deixa cada dono só ler.
- **Passe de batalha** na página da conta: dia N de 30, se o prêmio de hoje foi resgatado (`passe.ultimo`
  é o dia do jogo: dias desde 1970 no fuso de Brasília), total de resgates e trilhas completas.
