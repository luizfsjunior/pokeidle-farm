# Captura manual pelo worker (22/11/2026)

**Status:** aprovado e implementado em 22/11 (T1 a T18 em `test_protocol`, `test_ball_thrower`, `test_capture_target`
e `test_restock`). Falta deploy no servidor.

Pedido de 21/11: as contas 2 e 3 estão sem VIP. Para conta sem VIP, a bola automática do jogo responde
"Lançar pokebola é um recurso VIP". Com isso, o `capture_target` fica religando o `auto.set` a cada 30 s e nunca captura.
O worker passa a **jogar a bola ele mesmo** (`ball.throw`), em todas as contas, com ou sem VIP. É um padrão só
e dá menos código.

## Como funciona no jogo (confirmado em 22/11, `luizfsjunior_2` sem VIP)

- `{"t":"ball.throw","ballId":1,"slot":67}` é aceito sem VIP. A resposta é um `batalha` com
  `{"k":"bola","ballId":1,"slot":67,"sucesso":false,"chance":0.004,"shiny":false}` e `{"k":"fugiu",...}`, e
  depois um `estado` com `balls`.
- O corpo fica **30 s** no chão (`TEMPO_CHAO_MS`) e aceita **uma bola só**. Se ela falha, o pokémon foge. Entre um
  arremesso e outro, a espera é de 1,2 s (wiki).
- O `slot` é o mesmo da `morte`. A espécie (`n`), o nível (`nv`) e o shiny (`sh`) chegam antes, nos frames
  `campo` (`mobs[]`, com a chave `s` = slot). A qualidade, os IVs e a potência só aparecem no `capturado`.
- Bolas (`catalogoBolas`): Poke 1 (×1, 5), Great 2 (×2, 20), Super 3 (×3, 50), Ultra 4 (×4, 130),
  **Beast 5 (×8, não se compra com ouro)**. Não existe bola acima da Beast.

## Regras (decididas pelo usuário)

1. **Captura ativada** (`capture.start`): o worker joga uma bola em **todo corpo da espécie-alvo**. Continua
   até o `count` ou o `until`, como já funciona hoje. A bola é **a que valer a pena** (padrão) ou **a escolhida no
   painel**.
2. **Bolas sempre no bolso**: o `restock` repõe **toda bola comprável (1 a 4) abaixo de 100**, em toda conta.
3. **Shiny, sempre**: em qualquer conta, em qualquer hunt, a qualquer momento, com ou sem captura ativada. Caiu um
   shiny (de qualquer espécie): o worker joga a **melhor bola em estoque, até a Beast**.
4. **Sem bola automática**: o worker não liga mais `autoBallSemParar`/`autoBallAteCapturar` e mantém as duas
   desligadas. Assim, uma conta VIP não joga duas bolas.

## Propostas (aprovadas em 22/11)

- **P1. "Valer a pena"** usa a mesma regra do `restock` (`_ball_choice`): a bola de maior `catchRate` com preço ≤
  ouro líquido médio por abate (janela de 200 abates). Enquanto não houver dados (< 50 abates), usa a Poké Ball.
- **P2. Bola escolhida sem estoque**: usa a melhor bola abaixo dela que tiver estoque. Se não tiver nenhuma, não
  joga naquele corpo.
- **P3. Reposição**: abaixo de 100, compra até 100 (as bolas 2 a 4) e até 1.000 a Poké Ball. Respeita a
  `gold_reserve` e o teto `max_gold_per_hour` do `restock`.
- **P4. Onde fica o código**:
  - o tradutor guarda `slot → {nome, nv, sh}` dos frames `campo`, só em memória, sem gravar evento, e põe `slot` e
    `shiny` no evento `kill`;
  - um plugin novo, `ball_thrower`, ligado por padrão em toda conta, tem **a fila de arremessos** (shiny +
    captura ativa);
  - o `capture_target` deixa de mexer no `auto.set` e só informa a espécie-alvo e a bola.
- **P5. Shiny sem nenhuma bola em estoque**: grava `ball_thrower.shiny_missed` para alertar no painel.
- **Fora do escopo**: o `rank` e o foco `capture` do `restock` também usam a bola automática. Por enquanto, os dois
  só desligam as flags de bola (regra 4). Passar os dois para o arremesso manual fica para um pedido próprio.

## Bola em tudo no arremesso manual (25/11)

A regra 3 parte de uma premissa errada: a wiki do jogo (`pokepedia.mjs`, capítulo de shiny) diz que **o brilho é
sorteado no arremesso**, não dá para saber antes, e um shiny que escapa vai embora com o corpo. Então o corpo quase
nunca chega marcado como shiny, e o worker não jogava bola fora da captura ativa: 0 shiny nas contas até aqui.

Com isso, a "bola em tudo" (`catch_all`, o `restock` no foco `capture`) passou ao arremesso manual:

- o `restock` publica `state.catch_all` (o foco efetivo é `capture`; no `rank`, só quando ele cai no fallback
  `capture`) e zera `catch_all` e `worth_ball` ao parar;
- o `ball_thrower` joga a `worth_ball` em **todo corpo** quando `catch_all` está ligado. Sem `worth_ball` (menos de
  50 abates ou nenhuma bola se paga), não joga. A espécie da captura ativa continua com a bola dela;
- a reposição e o teto de gasto por hora seguem os do `restock` (P3).

Conta da chance: shiny por arremesso = 1/24.000 × chance da bola. Com a Ultra num 1º estágio (1,46%), ~1,6 milhão de
corpos por shiny. O Depot enche mais rápido (~200 capturas por dia por conta); por ora o usuário esvazia na mão.

## Casos de teste

Tradutor:
- T1. `campo` com `mobs:[{s:67,n:"Pichu",nv:260,sh:1}]` e depois `morte` com `slot:67` → o `kill` sai com
  `slot: 67` e `shiny: true`.
- T2. `morte` de um slot que não apareceu em nenhum `campo` → o `kill` sai com `slot` e `shiny: false`.
- T3. O slot que aparece em `fora[]` sai do mapa (ele não cresce sem limite).

`ball_thrower`:
- T4. Captura ativa (alvo Pichu, bola 1), `kill` de Pichu não shiny → manda `ball.throw {ballId:1, slot}`.
- T5. Captura ativa (alvo Pichu), `kill` de outra espécie não shiny → não joga.
- T6. Sem captura ativa, `kill` não shiny → não joga.
- T7. `kill` shiny, sem captura ativa, estoque `{1:95, 4:30, 5:10}` → joga a bola 5.
- T8. `kill` shiny com estoque `{1:95, 4:30}` → joga a bola 4. Com `{1:0, 2:0}` → não joga e grava
  `ball_thrower.shiny_missed`.
- T9. `kill` shiny da espécie-alvo durante a captura → uma bola só, a melhor (a regra do shiny ganha).
- T10. Dois `kill` no mesmo instante → o segundo `ball.throw` sai ≥ 1,2 s depois do primeiro.
- T11. Corpo que esperou na fila mais de 30 s desde o `kill` → é descartado sem arremesso.
- T12. Bola escolhida 4 sem estoque, com `{1:50, 3:10}` → joga a 3 (P2).
- T13. Bola "valer a pena": ouro líquido médio de 60 por abate → joga a Super (3). Com menos de 50 abates na janela
  → joga a Poké (P1).

`capture_target`:
- T14. Ao iniciar, não manda `auto.set` com bola ligada. Se a automação estiver com uma flag de bola ligada, manda
  um `auto.set` que desliga as duas, uma vez.
- T15. `count` e `until` continuam encerrando como hoje (os testes atuais passam).

`restock`:
- T16. Estoque `{1:80, 2:150, 3:0, 4:99}` com ouro sobrando → compra a 1 até 1.000, a 3 até 100 e a 4 até 100. Não
  compra a 2.
- T17. Nunca tenta comprar a bola 5.
- T18. Com o ouro na `gold_reserve`, não compra.
