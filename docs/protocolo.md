# Protocolo WebSocket do pokeidle.io

> 🟡 Mapeamento inicial baseado no código do [DiuleJR/pokeidle-manager-online](https://github.com/DiuleJR/pokeidle-manager-online) (commit `ca6e7f0`, 10/11/2026). Créditos ao autor, que fez esse trabalho de engenharia reversa.
>
> ✅ Em **12/11/2026** o worker rodou pela primeira vez contra o jogo (IP residencial, `observe_only`, conta nível 2 na hunt `magikarp`). O que foi visto nessa sessão está marcado como confirmado, e a seção [Observado na sessão real](#observado-na-sessão-real) traz o que o mapeamento original não tinha. O resto continua ⬜.
>
> Este repositório também é AGPL-3.0 ([ADR 0009](decisions/0009-licenca-agpl.md)). Código reaproveitado de lá deve manter o aviso de origem no arquivo.

> ⚠️ Nunca cole aqui tokens, cookies ou mensagens com dados de conta. O repositório é público.

## Convenções

- Todas as mensagens são JSON com um campo `t` (tipo).
- Eventos de combate chegam agrupados num frame `t: "batalha"`, com uma lista `ev` em que cada item tem um campo `k` (tipo do evento).
- O estado da conta chega inteiro no `welcome` e depois em patches parciais (`t: "estado"`).

## Conexão

| Item | Valor | Confirmado |
|---|---|---|
| URL | `wss://pokeidle.io` | ✅ |
| Heartbeat | ping de WebSocket a cada 30 s; sem pong em 90 s, a conexão é dada como morta (valores do DiuleJR) | ⬜ |
| Tamanho de frame | o `welcome` é um snapshot grande (**~450 KB** numa conta nível 2), então é preciso desligar o limite de tamanho (`max_size=None`) | ✅ |

## Sessão e token

O jogo guarda a sessão no `localStorage` de `pokeidle.io`:

| Chave | Conteúdo |
|---|---|
| `sessao` | JSON com `nick` e `token` (entre outros) |
| `id-dispositivo` | identificador aleatório do navegador |

Para extrair, rode no console do navegador, com o jogo aberto e logado:

```js
const s = JSON.parse(localStorage.getItem('sessao'));
console.log({ nick: s.nick, token: s.token, dispositivo: localStorage.getItem('id-dispositivo') });
```

### Passo a passo para extrair o token de várias contas

1. Use **um perfil do Chrome ou uma janela anônima por conta**. Logar uma segunda conta no mesmo perfil sobrescreve a `sessao` da primeira.
2. Entre em pokeidle.io/app e faça o login na mão (o Turnstile aparece normalmente).
3. Abra o console (F12), rode o comando acima e guarde `nick`, `token` e `dispositivo` no `.env` ou no painel. **Nunca no repositório.**
4. **Feche a aba ou a janela sem clicar em "Sair".** Sair provavelmente invalida o token (a confirmar), e uma aba aberta disputa a sessão com o worker (close 4001).
5. Repita para cada conta de farm.

Sem computador? O [deploy.md](deploy.md) tem um bookmarklet para extrair o token pelo celular.

As senhas ficam no gerenciador de senhas, nunca no worker (ver [ADR 0007](decisions/0007-contas-farm-email-senha.md)).

Comportamento conhecido:
- A sessão dura **cerca de 30 dias**.
- O servidor renova o token sozinho com a mensagem `sessao.renovada`. **É preciso guardar o token novo**, senão o antigo vence.
- O mesmo token aberto em dois lugares derruba o outro com o close code **4001** ("login externo"). Na prática: **não abra a conta de farm no navegador enquanto o worker estiver rodando**. ✅ Confirmado: abrir o jogo no navegador derrubou o worker na hora, e ele parou em `NEEDS_LOGIN` sem reconectar.
- ✅ Abrir a conta no navegador e fechar a aba **sem "Sair"** não invalidou o token do worker: ao religar, ele reconectou com o token do Vault. É o jeito seguro de mexer na conta na mão (trocar de hunt, configurar automação): parar o worker, usar o navegador, fechar sem sair e religar.
- O `id-dispositivo` entra na detecção de multiconta (Termos, seção 9). Cada conta deve usar sempre o mesmo `dispositivo`. Não gere um novo a cada conexão.

## Handshake

```
cliente → { t: "hello", nick, token, delta: 1, dispositivo }
servidor → { t: "welcome", estado: {...}, hunts: [...], itensNossos: [...], mercado: {...} }
```

- `delta: 1` tem função desconhecida (valor observado).
- Frames que chegam antes do `welcome` podem ser ignorados.
- Espera de até 15 s pelo `welcome`.

### Campos úteis do `welcome`

| Campo | Conteúdo |
|---|---|
| `estado.nick`, `estado.level` | identificação e nível |
| `estado.huntSlug` | hunt atual |
| `estado.pokemons[]`, `estado.activeId` | pokémons e o ativo |
| `estado.items` | inventário `{id: quantidade}` |
| `estado.automation` | config da automação do próprio jogo |
| `estado.centroLivreEm` | horário do servidor em que a trava de combate acaba |
| `estado.servidorAgora` | relógio do servidor (ms), para calcular o offset |
| `hunts[]` | hunts disponíveis (`slug`, ...) |
| `itensNossos[]` | itens próprios do servidor (ids ≥ 70000: nome, ícone, categoria, raro) |
| `mercado` | catálogo e limites do Mercado (preço mínimo, espera de compra) |

## Erros e recusas

Recusas chegam como `{ t: "erro", chave: "..." }`:

| `chave` | Significado | O que fazer |
|---|---|---|
| `auth.sessaoInvalida`, `auth.precisaLogin` | token inválido ou vencido | marcar `needs_login`, **não reconectar** |
| `auth.contaBanida` | conta banida (pode vir `motivoBan`) | parar a conta |
| `auth.ipBanido`, `auth.provedorBanido` | rede ou provedor banido | parar tudo naquela rede |
| `auth.contaExcluida` | conta excluída | parar a conta |
| `login.precisaNick` | conta sem nick | escolher o nick no jogo |
| `login.limiteOnlineIp`, `login.limiteOnlineIpLista` | rede no limite de contas online | tentar de novo em ~30 s |

Close codes:

| Código | Significado |
|---|---|
| 4001 | login externo (token aberto em outro lugar), confirmado pelo DiuleJR |
| 4003, 1008 | tratados como rejeição; causa não documentada (4003 pode ser provedor banido) |
| HTTP 401/403 no upgrade | credencial rejeitada |

Depois de uma rejeição, o DiuleJR espera 5 min antes de tentar de novo. Em quedas comuns de rede, espera 10 s.

## Mensagens servidor → cliente

| `t` | Conteúdo |
|---|---|
| `welcome` | snapshot completo (ver acima) |
| `estado` | patch parcial. ✅ O formato real é **aninhado**: `{ t: "estado", estado: { ...campos alterados } }`. `pkMud` (pokémons alterados, merge por `id`), `pkFora` (ids que saíram) e `huntSlug` ficam **dentro** de `estado`, não no topo |
| `batalha` | `ev[]` com eventos de combate (ver abaixo) |
| `campo.init` | entrou num mapa (`mapa`, `slug`). ✅ No Centro Pokémon vem `slug: "centro"` e `centro: true`, o que **não é uma hunt** |
| `sessao.renovada` | token novo em `token` |
| `erro` | recusa (ver acima) |
| `orbs` | resposta da carteira de Gemas |

### Eventos de `batalha` (campo `k`)

| `k` | Campos | Uso |
|---|---|---|
| `hunt` | `slug`, `nome` | confirmação da troca de hunt |
| `ataque` | `slot`, `hpAlvo` | dano no selvagem |
| `morte` | `quem` (`selvagem`), `slot`, `nome`, `xpTreinador`/`xp`, `ouro`, `ouroVendaAuto`, `drops[]` | abate: XP, gold e drops (**base da telemetria**). ✅ Campos reais na [sessão real](#observado-na-sessão-real) |
| `bola` | `slot`, `ballId`, `sucesso`, `shiny`, `chance` | resultado de captura |
| `fugiu` | `nome`, `level` | o selvagem fugiu |
| `centro` | `motivo` | foi para o Centro Pokémon |
| `compra` | — | confirmação de `shop.buy` |
| `venda` | — | confirmação de venda |

Também aparecem `aviso`, `marketComprado` e `mktSorteio`, relacionados ao Mercado.

## Mensagens cliente → servidor

| `t` | Campos | Uso | Confirmado |
|---|---|---|---|
| `hello` | `nick`, `token`, `delta`, `dispositivo` | handshake | ✅ |
| `hunt.select` | `slug` | trocar de hunt (só funciona fora da trava de combate) | ⬜ |
| `centro.ir` | — | ir ao Centro Pokémon | ⬜ |
| `ball.throw` | `ballId`, `slot` | jogar bola no selvagem abatido (janela de ~30 s; intervalo de ~1,3 s entre arremessos) | ⬜ |
| `shop.buy` | `kind` (`item` ou `ball`), `id`, `qty` | comprar na loja do NPC. Ex.: `{"t":"shop.buy","kind":"ball","id":1,"qty":1}` e `{"t":"shop.buy","kind":"item","id":200,"qty":1}`. A resposta é um `estado` com `gold` e o mapa **inteiro** de `balls` (inclusive as zeradas) ou de `items`. Ainda não se sabe se vem também um `batalha` `k: compra` | ✅ (DevTools, 12/11/2026) |
| `shop.sellAllPokemons` | — | vender todos os pokémons do Depot | ⬜ |
| `auto.set` | o objeto `estado.automation` inteiro, com os campos alterados | configurar a automação nativa do jogo. **Sempre parta do objeto atual**, nunca monte do zero. ✅ Os campos vão **achatados no topo** da mensagem, não dentro de `automation`: `{"t":"auto.set","autoBallSemParar":false,"ballIds":[1,2,3,4],"autoPotion":true,"potionIds":[...],"hpLimiar":0.6,...}`, com **todos** os campos da `automation` (o navegador manda tudo mesmo mudando um só) | ✅ (DevTools, 12/11/2026) |
| `market.itens` | `elemento`, `categoria`, `elementos?` | listar itens do Mercado | ⬜ |
| `market.medias` | — | médias de preço | ⬜ |
| `market.item` | `itemId`, `moeda` | detalhe de um item | ⬜ |
| `market.listar` | `tipo`, `moeda`, `ordem` (`recentes`, `baratos`, `caros`), `busca`, filtros (`soShiny`, `soP5`, `ivMin`, ...), `pagina` | vitrine | ⬜ |
| `market.meus` | — | meus anúncios | ⬜ |
| `market.comprar` | `id`, `qtd`, `preco`, `moeda` | comprar um anúncio | ⬜ |
| `orbs.painel` | — | carteira de Gemas (somente leitura) | ⬜ |

## Regras que o worker tem que respeitar

- **Trava de combate:** `hunt.select` e `centro.ir` só funcionam depois de `estado.centroLivreEm`, e cada golpe recebido renova a trava. Coloque o pedido numa fila e envie quando a trava acabar.
- **Uma compra por vez:** espere o `k: "compra"` antes da próxima, e trate o caso de a confirmação não chegar (timeout).
- Nunca logar `token` nem credenciais.

## Observado na sessão real

Sessão de 12/11/2026, conta nível 2, ~10 min no Centro de Cerulean e depois na hunt `magikarp`. Os números valem para essa amostra; hunts de nível alto podem ter outro ritmo.

### `morte` de verdade

```json
{ "k": "morte", "quem": "selvagem", "slot": 12, "nome": "Magikarp",
  "xp": 8, "xpPokemon": 11, "xpTreinador": 11,
  "ouro": 41, "ouroLoot": 5, "lootBoost": true, "drops": [] }
```

- `xp` (8) é diferente de `xpPokemon`/`xpTreinador` (11). ✅ O `xp` é a base e os outros dois já vêm com os bônus: depois de ativar o VIP, `xp` continuou 8 e `xpPokemon`/`xpTreinador` foram para 16.
- `ouroLoot` (5) vem separado de `ouro` (41), junto com `lootBoost`. ✅ O `ouro` **já inclui** o `ouroLoot`: em 288 abates seguidos o `estado.gold` subiu exatamente 41 por abate. O `ouroLoot` é só a parte que veio do bônus de loot.
- `ouroVendaAuto` **não apareceu** nessa sessão (o tradutor grava 0).
- Nenhum drop em 53 abates de Magikarp, então o formato de `drops[]` continua desconhecido.
- **Ritmo:** 53 abates em 3 min, **~18 por minuto** (~1.000 por hora). O simulador usa 6 por minuto, que é um chute; com uma amostra só de Magikarp no nível 2 ainda não dá para trocar por um valor medido.

### Eventos de `batalha` que o mapeamento não tinha

| `k` | Exemplo | Uso |
|---|---|---|
| `spawn` | `slot`, `nome`, `level`, `hp`, `maxHp`, `tipos`, `speciesId`, `looktype` | um selvagem apareceu; vem um por abate |
| `levelup` | `quem: "treinador"`, `level` | subida de nível do treinador (provavelmente também de pokémon, com outro `quem`) |

`bola` e `fugiu` também foram confirmados, com a bola automática ligada:

```json
{ "k": "bola", "slot": 33, "ballId": 1, "chance": 0.003, "sucesso": false, "shiny": false }
{ "k": "fugiu", "nome": "Magikarp", "level": 1, "shiny": false }
```

- No modo "sem parar" sai **uma bola por abate**, e cada bola que falha vem seguida de um `fugiu`.
- A `chance` de 0,003 é o `piso` da tabela `captura` do `welcome` (Poké Ball em Magikarp), ou seja, uma captura a cada ~330 bolas.
- O estoque de bolas chega em `estado.balls` (`{"1": 56}`) a cada arremesso.
- ✅ **Captura com sucesso** (Ultra Ball, `ballId: 4`, chance de 0,012 em Magikarp): no mesmo frame vem o `bola` com `sucesso: true` e o `topCatchNova`, e uns 250 ms depois chega o `capturado` com o pokémon completo:

  ```json
  { "k": "capturado", "paraDepot": false,
    "pokemon": { "id": 128261620, "nome": "Magikarp", "speciesId": 129, "level": 1, "shiny": false,
                 "quality": 0.983, "potencia": 1, "lookShiny": null,
                 "ivs": { "hp": 19, "atk": 6, "def": 17, "spAtk": 27, "spDef": 28, "speed": 8 } } }
  ```

  Depois chega um `estado` com o pokémon novo no `pkMud`. O `topCatchNova` (`sp`, `chave`, `n`, `m`, `s`, `pontua`) parece ser o ranking de capturas da semana. `paraDepot` indica se o pokémon foi para o Depot.
- O `estado.dexMud` (`{"129": {"c": 1, "k": 502}}`) traz capturas (`c`) e abates (`k`) por espécie.
- **A bola automática exige VIP** no jogo. Sem VIP, as duas flags de bola da `automation` não ligam.
- **Quando as bolas acabam** (`estado.balls` = `{"1": 0}`), o jogo simplesmente para de jogar: não compra sozinho e não manda `aviso`. A hunt continua normalmente. Repor bolas fica por conta da fase 3 (`shop.buy`).

### Mensagens que o mapeamento não tinha

| `t` | Conteúdo | Observação |
|---|---|---|
| `campo` | `ts`, `seq`, `alvo`, `fora[]` e, quando mudam, `heroi`, `treinador` e `mobs[]` (posições no mapa) | tick de posição. ~1 por segundo no Centro. Na hunt, **~3 por segundo e ~6 MB por hora** (não apareceu na primeira conexão, só na segunda) |
| `vivo` | vazio | keepalive do servidor |
| `chat` | mensagem do chat global, **de outros jogadores** | ~45 por minuto. Não serve para telemetria e guarda conversa de terceiros |
| `chat.del`, `chat.fixada` | moderação do chat | — |
| `amigos` | `max`, `lista[]`, `pedidos[]` | logo depois do `welcome` |
| `pvp` | `fila`, `filaLogin` | logo depois do `welcome` |
| `shiny.captura` | `nick`, `pokemon{nome, level, speciesId}` | **anúncio global** de shiny capturado por qualquer jogador. Não é captura nossa |

### Volume (o que pesa na tabela `events`)

- O `estado` chega a **cada abate** com `xp`, `gold`, `centroLivreEm`, `dexMud` e o `pkMud` completo do pokémon ativo (~1 KB). São ~1.000 patches por hora por conta.
- O `welcome` tem ~450 KB e é gravado inteiro em cada conexão.
- O `chat` tem ~50 KB por 3 min.
- O `campo` na hunt é o maior de todos: ~140 KB em 1,4 min, ou ~6 MB por hora por conta.

### `welcome` além do que está na tabela acima

- `estado.automation`: config da automação nativa. Na sessão: `ballIds: [1]`, `autoBallSemParar: false`, `autoBallAteCapturar: false`, `autoPotion`, `autoRevive`, `autoVoltarHunt`, `autoLockShiny`, `autoLockNotaMin` e outros. Com as duas flags de bola desligadas, **nenhuma bola foi jogada**, por isso ainda não há `bola` nem captura real.
- `estado.balls` (`{id: quantidade}`), `estado.cheio`, `estado.noCentro`, `estado.selvagem`.
- Tabelas do jogo: `captura` (`base`, `piso`, `teto`, `porDegrau`), `catalogoBolas` (`id`, `nome`, `catchRate`, `priceGold`), `hunts[]` (~1.000 hunts, com `area`, `nivel`, `especies[]` e `totalSpawns`), `potencias`, `chanceShiny`, `economia` e outras.

## Pendências para confirmar

- [x] Conferir o `hello` e o `welcome` (sessão real de 12/11/2026)
- [ ] Ver se `delta` muda em algum caso
- [ ] Confirmar o `sessao.renovada` (quando chega?)
- [ ] Anotar o formato de `drops[]` dentro de `morte` (nenhum drop em Magikarp)
- [x] Ver um `bola` real (bola automática "sem parar", com VIP)
- [x] Ver uma captura com sucesso (`k: capturado`)
- [x] `ouro` × `ouroLoot` em `morte` (o `ouro` já inclui o `ouroLoot`)
- [x] Entender `xp` × `xpPokemon`/`xpTreinador` em `morte` (`xp` é a base)
- [ ] Medir o ritmo de abates numa hunt de nível alto
