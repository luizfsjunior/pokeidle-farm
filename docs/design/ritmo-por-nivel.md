# Ritmo por nível do pokémon ativo

Status: **implementado** (15/11/2026), aguardando deploy. Pedido do usuário: "o farm fica na mesma hunt quando o
pokémon aumenta de nível, então os stats aumentam e o cálculo melhora".

## Por quê

O ritmo de uma hunt era a média dos abates/h dos últimos 14 dias. Mas o pokémon ativo ganha a mesma XP que o
treinador a cada abate, sobe de nível, e o dano cresce: pela fórmula do jogo, ((2·nível/5 + 2) × poder × atk/def)/50 +
2, com atk ∝ nível. Do nível 16 ao 23 o dano por golpe quase dobra. A média histórica subestima as hunts onde a conta
fica, e mais ainda as "lentas" (60–115 abates/h), que estão longe do teto.

## O que foi feito

- **Tradutor:** acompanha os pokémon da conta (`welcome.estado.pokemons`, `activeId`, e o `pkMud` de cada `estado`) e
  carimba em cada abate `active_level` e `active_species_id`. Sem `activeId`, o ativo é o único pokémon do `pkMud` (quem
  ganha XP por abate).
- **Banco** (migration `20261115080000_active_level.sql`): métricas auxiliares `active_level_sum` e `kills_leveled` no
  `metric_hourly`; o `rank_hunt_stats` devolve `avg_active_level` (o nível médio em que o ritmo de cada hunt foi medido).
- **`PaceBook`** (`pace.py`): ritmo projetado = medido × f(L atual)/f(L da medição), f(L) = (0,4·L + 2)·L, limitado ao
  teto (o maior ritmo medido; a partir dele o limite é andar e reaparecer). Hunts já a 80% do teto não escalam.
- **`AccountStateView.active_level`** (do último abate) alimenta o `rank`, o `gems` e o potencial (`compute_potential`).

## Limitações

- Os abates de antes do deploy não têm nível: para eles o ritmo não é projetado (usa o medido).
- O fator ignora a troca de golpes ao subir de nível e a diferença física/especial; é uma aproximação de ordem de
  grandeza, corrigida pela própria medição conforme a conta farma.
- Trocar o pokémon ativo muda o ritmo de todas as hunts; o modelo considera só o nível, não a espécie (ver a
  proposta de equipar o ativo pela hunt em [analise-progressao-e-mercado.md](../analise-progressao-e-mercado.md)).

## Testes

`test_protocol.py` (abate com o nível do ativo, nível novo pelo `pkMud`, ativo deduzido do `pkMud`), `test_gems.py`
(projeção, teto, nível médio com abates da sessão, `rates_for` com o nível; `rank_hunt_stats` em memória com o nível
médio), `test_session.py` (`AccountStateView` com o nível do último abate) e `rank_hunt_stats_test.sql` (nível médio).
