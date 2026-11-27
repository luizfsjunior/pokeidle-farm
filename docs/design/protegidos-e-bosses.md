# Protegidos e bosses automáticos (épico C)

Pedido de 27/11 (frente 4 do backlog de 26/11, plano em `backlog-plano`). A lista de protegidos é a trava de
tudo que mexe na coleção: nada vende, sacrifica, oferece ou troca pokémon sem passar por ela. Os bosses
automáticos lutam no boss do prêmio escolhido enquanto houver Boss Token.

## C1 — Protegidos

**Quem é protegido** (`worker/src/pokeidle_farm/protection.py`, espelhado em `web/lib/protection.ts`):

| Motivo | De onde vem | Firme? |
| --- | --- | --- |
| `manual` | marcado no painel (tabela `protected_pokemon`) | sim |
| `shiny` | o próprio pokémon | sim |
| `equipe` | está num slot da equipe (é a equipe que luta nos bosses) | sim |
| `colecao` | está na Coleção do jogo (`automation.pokemonTravado`) | não |

"Firme" quer dizer que nem o painel manda para o Depot: é preciso tirar a marca antes. A Coleção é a marca
que o próprio jogador mexe (mandar para o Depot pelo painel é justamente tirá-la).

**Onde a regra vale hoje** (os únicos caminhos que tiram pokémon da conta):

- `depot.sell`: protegidos no Depot (shiny, manuais) vão para a Coleção antes da venda. Se o jogo não confirmar,
  não vende nada. Sem conseguir ler a lista, o comando falha (fail closed). O `allow_shiny` ficou sem efeito.
- `collection.move` para o Depot: um protegido sozinho → falha com "pokémon protegido"; em lote → os
  protegidos ficam onde estão e voltam em `result.protected`.
- `team.apply` / `team.move`: quem sai da equipe e é protegido vai para a Coleção, mesmo que o painel tenha
  pedido Depot.
- Plugin `protect` (sempre ligado): põe na Coleção do jogo todo protegido firme fora da equipe, um a cada
  20 s, relendo a lista a cada minuto. Assim a Auto Venda do próprio jogo também não leva (pergunta 3 do
  plano: espelhar na Coleção). Grava `protect.mirrored` (raro).

Os próximos (seller de pokémon B7, venda de repetidos F3, sacrifício/oferenda F4) chamam
`protection.is_protected` antes de agir.

**Banco**: `protected_pokemon (account_id, pokemon_id, note, created_at)`, só as marcas manuais, RLS do dono
para ler e escrever (o painel grava direto, como `team_drafts`). Não cresce com o tempo.

**Painel** (aba da conta, Pokémons): 🔒 no card de quem é shiny ou marcado, filtro "Só protegidos", botões
"Proteger"/"Tirar a proteção" na ficha (com o motivo) e na seleção em lote. A venda do Depot conta só os
não protegidos.

## C3 — Protocolo do boss (lido, não visto ao vivo)

Do `app.js` (27/11) e do welcome guardado em `events` (12/11):

- `bossesJogaveis` no welcome: por boss `key`, `regiao`, `degrau`, `posicao`, `entrada` {itemId 70000 =
  Bronze Boss Token, qtd 1}, `teamLevel`, `equipeIdeal` (5), `minNivelTreinador`. Kanto 300, Johto 650,
  Hoenn 3.100, Sinnoh 9.750... O worker passou a guardar em `game_catalog` (regras) e no `catalog.rules`.
- `estado.boss` = {auto, autoKey, arena, pontos, vitorias{key: n}} (já vai para `account_profile.extra`).
- Botões: "Desafiar" manda `{t: "boss.entrar", key}`; a caixa "Repetir" manda `{t: "boss.auto", ativo, key}`;
  "Abandonar" manda `{t: "boss.sair"}`.
- Penalidade (`penalidadeDaMinhaEquipe`): força = Σ min(1, nível/teamLevel) da equipe; o dano tomado é
  multiplicado por 3^(equipeIdeal − força). Com os 5 no nível, ×1; com um a menos, ×3.
- O prêmio gira por posição no trio a cada dia sazonal (18:00 de Brasília), a partir de 17/11.

Falta ver ao vivo: a resposta do `boss.entrar`, o fim da luta e o prêmio, se a repetição entra sozinha
depois de ligada, e como a caça fica enquanto a conta está na arena (vigia de "sem abates", hunt_hold).

## C4 — Plugin `boss`

Desligado por padrão. Config: `prize` (tm, mega, tickets; padrão mega), `region` ("auto" ou uma região),
`max_mult` (1 = os 5 no nível), `min_tokens`, `dry_run` (padrão **true**), `check_s`, `enter_every_s`.

A cada minuto escolhe o boss (`boss_model.choose`): o do prêmio de hoje na região mais alta em que o
treinador entra e a equipe aguenta. Se pode lutar, liga a repetição nele e entra se não estiver na arena; se
a equipe deixou de aguentar, desliga a repetição que ele mesmo ligou (sem token o jogo para sozinho). Em
ensaio grava `boss.would` com a mensagem que mandaria, uma vez por decisão. `boss.plan` só quando a
escolha muda.

Em 27/11 nenhuma conta passa: todos os treinadores entram em Kanto (300), mas cada equipe tem só 1 pokémon
no nível 300 (a da _1 toma ×8 de dano). Ligar em ensaio já mostra o que faria quando a equipe chegar.

## C5 — Card na /bosses

Para a conta escolhida: ligar/desligar, ensaio, prêmio, tokens, quantos da equipe estão no nível da região e
o multiplicador de dano, a repetição no jogo, as vitórias e a última decisão do plugin.

## Riscos

- O protocolo do boss nunca foi mandado pelo worker. O ensaio é o padrão; o primeiro uso de verdade deve ser
  acompanhado (um token, olhando o painel).
- Enquanto a conta luta no boss, plugins de caça podem querer trocar de hunt. A ver no primeiro uso ao vivo.
