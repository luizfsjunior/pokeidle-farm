# Treinar a equipe (`team_train`) e equipe pelo painel

Status: **implementado** (17/11/2026), ainda não testado contra o jogo.

## Por quê

Os bosses pedem **5 pokémon com o nível do boss** (Kanto: 300); para cada um que falta, o dano tomado ×3
([foco-outland.md](foco-outland.md)). Só o pokémon ativo ganha XP cheio. A Casa e o item Exp. Share dividem XP com
a equipe, mas a Casa sai de 10 Key Fragments e o Exp. Share custa diamantes. Sem gastar, o caminho é **trocar o
ativo**: subir um de cada vez.

## Mensagens (do `app.js`, 17/11)

- `team.active {pokemonId}`: troca o ativo.
- `team.move {pokemonId, slot}`: põe na equipe (slot 0 a 4) ou tira (`slot: null`).

Também no `app.js`: `boss.entrar {key}`, `boss.auto {ativo, key}`, `boss.sair`, `outland.tier {tier}`,
`market.comprar`, `sacrificio.sacrificar`, `xpshareheld.equipar` (ainda sem uso no worker).

## O plugin `team_train`

Config: `target_level` (300), `finish_on_strongest` (sim), `confirm_s` (60).

A cada estado ou abate:
1. Membros da equipe abaixo do alvo? Se o ativo é um deles, segue treinando.
2. Se o ativo chegou no alvo (ou não está na equipe), troca para o **membro mais fraco** abaixo do alvo.
3. Todos no alvo: volta para o **mais forte** e grava `team_train.done` uma vez.

Espera o ativo mudar até `confirm_s`; sem mudar, grava `team_train.failed` e tenta de novo. Eventos:
`team_train.switch {from, to, reason, target_level, team}`, `team_train.failed`, `team_train.done`.

O foco XP (`gems`) **replaneja quando o ativo muda** (`gems.plan` com `reason: active_changed`): um ativo fraco vai
para uma hunt que ele aguenta. O worker passou a enxergar a equipe: o tradutor guarda o `slot` de cada pokémon e a
sessão copia para `state.team`.

## Painel

- Aba **Equipe e coleção**: em cada pokémon da equipe, **Tornar ativo** e **Tirar**; nos de fora, **Pôr na equipe**
  (no primeiro slot livre). Comandos `team.active` e `team.move` (migration `20261117010000_commands_team.sql`).
- Aba **Estratégia**: card **Treinar a equipe**, com o nível alvo e Ligar/Desligar (`plugin.set` do `team_train`).

## Riscos

- Logo depois da troca, o ativo fraco ainda está na hunt do anterior até o foco XP mudar de hunt (alguns segundos,
  com a trava de combate): pode tomar dano ou cair nesse meio-tempo.
- Um pokémon que não ataca bem (Magikarp antes de evoluir) sobe devagar: escolha a equipe pensando nisso.
- Sem foco XP ligado, o `team_train` troca o ativo mas ninguém escolhe a hunt.
