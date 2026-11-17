# Foco XP: buscar a pedra de evolução

Status: **implementado** (17/11/2026).

## Problema

O foco XP evoluía o ativo só quando a pedra do tipo já estava na bolsa. As hunts de mais XP para o Bulbasaur são de
Pedra e Terra (Kabuto, Graveler, Onix), que dropam Rock e Earth Stone, nunca Leaf Stone. Resultado: o inicial ficava na
primeira forma, com stats e golpes fracos, e a subida inteira atrasava (o plano já mostrava 26 h sem evolução contra
21 h com).

## Regra

Quando o ativo está a `stone_lead_levels` níveis (padrão 2) ou menos do nível de evoluir e a pedra do tipo (o `type1`)
não está na bolsa, o foco XP vai para a hunt **que mais dropa essa pedra por hora**:

```
pedras/h(hunt) = abates/h projetados do ativo × chance da pedra pelo estágio do selvagem (0,2% / 0,35% / 0,5%)
```

Só entram hunts liberadas cujo selvagem tem o tipo da pedra (Leaf Stone: Grama). Empate: a de mais XP/h. A troca ignora
a folga de 15% do foco XP. Sem nenhuma hunt que dropa a pedra, segue a rota de XP normal.

Quando a pedra cai (`state.patch` com o item na bolsa), o plugin grava `progress.stone_found`, tenta evoluir na hora
(se o ativo já está no nível) e refaz o plano, voltando para a hunt de XP. Se a pedra caiu antes do nível (por causa da
antecedência), ela fica guardada e o `maybe_evolve` evolui ao chegar no nível, como antes.

O seller guarda 5 de cada pedra, então a pedra buscada não é vendida.

## Eventos

- `gems.plan` (foco XP) ganha `stone_hunt`: `{stone, evolve_level, active_level, hunt, name, chance,
  stones_per_hour, hours_expected, options}`, ou `null`.
- `progress.stone_hunt`: começou a buscar uma pedra (os mesmos campos).
- `progress.stone_found`: `{stone, hunt}`.

## Plano até o 150

O simulador (`plan_to`) faz o mesmo: sem a pedra, a fase vira busca (`Phase.stone`) na hunt de mais pedras/h e dura o
tempo esperado até cair uma (1 ÷ pedras/h), com a XP ganha nesse tempo. A evolução registra `farm_hours`. O card mostra
"Buscando Leaf Stone…" e, no plano, quanto tempo a busca custa.

## Configuração (`GemsConfig`)

- `farm_stone` (ligado): desliga a busca.
- `stone_lead_levels` (2): quantos níveis antes do de evoluir a busca começa.

## Fora por enquanto

- Comprar a pedra no Mercado (`market.comprar`, formato ainda não confirmado; as pedras estão a 2 gemas, mas a conta
  de teste não tem gemas).
- Passar a pedra de outra conta do farm.
