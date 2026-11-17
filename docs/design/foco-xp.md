# Foco XP (subir de nível)

Status: **implementado** (15/11/2026). Vem da [análise de progressão](../analise-progressao-e-mercado.md): o dinheiro
de verdade (Outland, shiny, pokémon fortes) pede nível; subir de nível é o foco que mais acelera a conta.

## Como escolhe a hunt

```
XP/h(hunt) = abates/h projetados × XP por abate
```

- **Abates/h projetados**: o ritmo medido na hunt, projetado para o nível atual do pokémon ativo
  ([ritmo-por-nivel.md](ritmo-por-nivel.md)). Hunt nunca medida usa a **previsão do simulador de combate** para o
  pokémon ativo (origem `model`; [simulador-1-combate.md](simulador-1-combate.md)), que enxerga a vantagem de tipo; sem
  previsão (falta a Pokedex, as regras do `welcome` ou o perfil do ativo), a do mesmo nível ou a do nível medido mais
  próximo abaixo. Ao entrar na hunt prevista, o ritmo medido substitui a previsão (`GemsConfig.use_model`, padrão
  ligado).
- **XP por abate**: a medida na própria hunt (com 30 abates ou mais; já vem com os bônus de VIP, evento etc.); senão a
  fórmula do jogo, ⌊0,6 × nível²⌋ + 8, vezes o bônus medido da conta (XP real ÷ XP da fórmula nas hunts medidas).
- Troca de hunt só se a melhor render mais que `1 + hysteresis` (15%) da atual, com o mesmo `HuntSwitcher` do foco gemas
  (trava de combate, timer, confirmação).

## Onde fica

É o plugin `gems` com `objective: "xp"` (o mesmo ciclo, a mesma troca de hunt, outro valor): `xp_model.py` calcula as
opções; o `rank_hunt_stats` devolve a XP por hunt (migration `20261115090000_hunt_stats_xp.sql`). O `gems.plan` traz
`objective: "xp"`, o nível do ativo e as 5 melhores hunts em XP/h.

**No painel:** "XP (subir de nível)" no card Foco manda `focus.set` com `focus: "xp"`: `restock` em `gold_xp_drop`
(bolas desligadas; o ouro fica para poções), `rank` desligado, `gems` ligado com `objective: "xp"`.

## Plano até o 150 e evolução

No foco XP o plugin também grava o plano até o nível 150 (`progress.plan`), vai buscar a pedra de evolução que falta
([foco-xp-pedra.md](foco-xp-pedra.md)) e evolui o ativo quando chega o nível e há
pedra: ver [simulador-2-progressao.md](simulador-2-progressao.md).

## Testes

`test_gems.py` (fórmulas de XP e da curva, XP medida contra fórmula com o bônus da conta, plugin com objetivo XP),
`test_commands.py` (`focus.set` xp) e `rank_hunt_stats_test.sql` (XP por hunt).

## Próximo

Equipar o pokémon ativo pela hunt (`team.active {pokemonId}`, 3 s entre trocas): adiado até a conta ter um segundo
pokémon forte; em 15/11 o Bulbasaur 24 ganha em todas as hunts por 4–30× (simulação).
