# Simulador, camada 4: decisões até o nível 150

Status: **implementado** (16/11/2026). Base: as camadas 1 a 3 ([combate](simulador-1-combate.md),
[progressão](simulador-2-progressao.md), [captura](simulador-3-captura.md)).

## Pergunta

Com o que a conta ganha jogando (ouro/Coins, pedras, prêmios grátis; diamantes e gemas compradas ficam de fora), o que
mais acelera a ida ao treinador 150, além da hunt e do ativo que as camadas 1 e 2 já escolhem?

## Inventário das alavancas (código público v1.420.0)

| Alavanca | Como se consegue | Efeito | Veredito até o 150 |
|---|---|---|---|
| Hunt pela vantagem de tipo | — | o que mais pesa no ritmo | **feito** (camadas 1 e 2, foco XP) |
| Evolução do inicial | nível + 1 pedra do tipo | stats e golpes da forma nova | **feito** (evolução automática) |
| Poção de menor custo por HP | ouro (NPC) | menos ouro por HP | **feito** (restock `potion_auto`) |
| Poção sem teto por hora | — | não fica sem poção | **feito** (foco XP) |
| **Passe de batalha grátis** | resgate diário (nível 10+) | Coins (250 mil a 5 mi), boosts de XP (dias 3, 14, 29) e de XP do pokémon (9, 26), revives, bolas, Boss Token (dia 30) | **feito**: plugin `daily` |
| **Dia sazonal** | todo dia, um tipo | o pokémon do tipo do dia bate ×2 e apanha ÷4 (vale para os selvagens) | **feito**: simulador, foco XP e plano |
| Capturar outro ativo | bolas | — | não: o inicial ganha de quase tudo (camada 3) |
| Sacrifício (×1,2 XP) | pokémon com nota ≥ 3,5 | boost de XP | não: ~1 em 3 a 10 mil capturas tem nota 3,5 (camada 3) |
| Refino (+1 stat base) | pedras do tipo: +N custa 500·N³ | +1 por degrau | não: +1 = 500 Leaf Stones |
| Mystery Egg P2/P3/P4 | 20 mi / 120 mi / 250 mi de Coins | pokémon com potência garantida | não: a conta chega ao 150 com ~4 mi |
| TM Elemental (Z-Move, poder 2.800) | fragmentos dos bosses lendários | golpe enorme a cada 60 s | depois: bosses pedem time forte |
| Bicicleta (+100% a +250% no passo) | fragmentos da Outland | menos caminhada | depois do 150 |
| Boost de guild (+10% XP) | banco da guild em diamantes | XP | fora (diamantes) |
| Boost dos Atrasados (×10 XP) | loja de diamantes | XP | fora (diamantes) |
| Passe VIP, chocadeira extra, bulbo | diamantes | — | fora |

## Implementação

- **Plugin `daily`** (`plugins/daily.py`): no dia do passe (vira às 03:00 UTC), se `estado.passe.ultimo` não é hoje e o
  treinador tem nível 10+, manda `passe.resgatar`; confirma quando o `ultimo` vira hoje (`daily.claimed`) ou grava
  `daily.failed` depois de 60 s e tenta de novo em 30 min. Ligado por conta (`strategy_configs`), não sempre ligado:
  só a conta de teste por enquanto. Os boosts que o passe dá entram no `estado.bonusXp`, que o plano já lê.
- **Dia sazonal** (`dia-sazonal.mjs`): o tradutor guarda `estado.diaSazonal` ({tipo, fim}); `AccountStateView.season_type()`
  devolve o tipo enquanto vale. No simulador, `season_factor` multiplica o dano pelos tipos do pokémon (quem é do tipo
  bate ×2; quem é do tipo apanha ÷4), nos dois sentidos; o foco XP prevê as hunts não medidas com o tipo do dia e o
  plano o aplica até o fim do dia no relógio simulado.
- **Ritmo medido no dia sazonal** (corrigido em 16/11): o ritmo medido vem de dias normais, então o foco XP o multiplica
  pela razão entre a previsão com o tipo do dia e a previsão sem ele (`model/predict.season_adjust`; origem
  `measured_season`, "medido, ajustado ao dia sazonal" no painel). O `ModelRates` guarda as duas previsões em cache.
- **Abates do dia sazonal fora do histórico** (16/11, migration `20261116010000_season_pace.sql`): cada abate carimba
  `season` (o tipo do dia, enquanto vale). O `refresh_metric_hourly` guarda à parte os números dos abates afetados (o
  tipo do dia é um dos tipos do ativo ou da espécie da hunt, pelo `game_species`): `kills_season`,
  `active_minutes_season`, `xp_season`, `active_level_sum_season` e `kills_leveled_season`; o `rank_hunt_stats` os
  desconta, então o ritmo medido é o de dias normais. As métricas totais não mudam (o painel segue contando tudo). Na
  sessão, o plugin gems também deixa os abates afetados fora do `PaceBook` (`_season_hit`, a mesma regra).

## Testes

`tests/test_daily.py` (virada do dia às 03:00 UTC, resgate único, confirmação, falha e nova tentativa) e
`tests/test_combat_model.py` (fator sazonal, efeito no ritmo, correção do ritmo medido e os dois caches),
`tests/test_gems.py` e `test_protocol.py` (carimbo e filtro na sessão) e `supabase/tests/season_pace_test.sql`.

## Próximo

- Conferir o primeiro resgate do passe e o boost de XP do dia 3 (se entra sozinho no `bonusXp` ou se precisa ser ativado).
- Ligar o `daily` nas outras contas de farm (pedir ao usuário).
- Depois do 150: Outland (fragmentos, bicicleta), bosses (TM Elemental) e o Mercado de pokémon.
