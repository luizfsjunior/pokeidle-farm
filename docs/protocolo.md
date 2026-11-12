# Protocolo WebSocket do pokeidle.io

> 🟡 Mapeamento inicial baseado no código do [DiuleJR/pokeidle-manager-online](https://github.com/DiuleJR/pokeidle-manager-online) (commit `ca6e7f0`, 10/11/2026). Créditos ao autor, que fez esse trabalho de engenharia reversa. **Ainda precisa ser confirmado por nós no DevTools** (coluna "Confirmado").
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
| URL | `wss://pokeidle.io` | ⬜ |
| Heartbeat | ping de WebSocket a cada 30 s; sem pong em 90 s, a conexão é dada como morta (valores do DiuleJR) | ⬜ |
| Tamanho de frame | o `welcome` é um snapshot grande, então é preciso desligar o limite de tamanho (`max_size=None`) | ⬜ |

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
- O mesmo token aberto em dois lugares derruba o outro com o close code **4001** ("login externo"). Na prática: **não abra a conta de farm no navegador enquanto o worker estiver rodando**.
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
| `estado` | patch parcial em `estado`; `pkMud` = pokémons alterados (merge por `id`), `pkFora` = ids que saíram da lista |
| `batalha` | `ev[]` com eventos de combate (ver abaixo) |
| `campo.init` | entrou num mapa (`mapa`, `slug`) |
| `sessao.renovada` | token novo em `token` |
| `erro` | recusa (ver acima) |
| `orbs` | resposta da carteira de Gemas |

### Eventos de `batalha` (campo `k`)

| `k` | Campos | Uso |
|---|---|---|
| `hunt` | `slug`, `nome` | confirmação da troca de hunt |
| `ataque` | `slot`, `hpAlvo` | dano no selvagem |
| `morte` | `quem` (`selvagem`), `slot`, `nome`, `xpTreinador`/`xp`, `ouro`, `ouroVendaAuto`, `drops[]` | abate: XP, gold e drops (**base da telemetria**) |
| `bola` | `slot`, `ballId`, `sucesso`, `shiny`, `chance` | resultado de captura |
| `fugiu` | `nome`, `level` | o selvagem fugiu |
| `centro` | `motivo` | foi para o Centro Pokémon |
| `compra` | — | confirmação de `shop.buy` |
| `venda` | — | confirmação de venda |

Também aparecem `aviso`, `marketComprado` e `mktSorteio`, relacionados ao Mercado.

## Mensagens cliente → servidor

| `t` | Campos | Uso | Confirmado |
|---|---|---|---|
| `hello` | `nick`, `token`, `delta`, `dispositivo` | handshake | ⬜ |
| `hunt.select` | `slug` | trocar de hunt (só funciona fora da trava de combate) | ⬜ |
| `centro.ir` | — | ir ao Centro Pokémon | ⬜ |
| `ball.throw` | `ballId`, `slot` | jogar bola no selvagem abatido (janela de ~30 s; intervalo de ~1,3 s entre arremessos) | ⬜ |
| `shop.buy` | `kind` (`item` ou `ball`), `id`, `qty` | comprar na loja do NPC | ⬜ |
| `shop.sellAllPokemons` | — | vender todos os pokémons do Depot | ⬜ |
| `auto.set` | o objeto `estado.automation` inteiro, com os campos alterados | configurar a automação nativa do jogo. **Sempre parta do objeto atual**, nunca monte do zero | ⬜ |
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

## Pendências para confirmar no DevTools

- [ ] Abrir pokeidle.io/app → F12 → Network → WS e conferir o `hello` e o `welcome`
- [ ] Ver se `delta` muda em algum caso
- [ ] Confirmar o `sessao.renovada` (quando chega?)
- [ ] Anotar o formato de `drops[]` dentro de `morte`
