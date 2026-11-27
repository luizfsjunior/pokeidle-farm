# worker

Worker headless do pokeidle-farm. A visão geral, as decisões e o design estão em [../README.md](../README.md) e [../docs/](../docs/). O design desta fase está em [../docs/design/fase-2.md](../docs/design/fase-2.md).

> O worker conecta, mantém a sessão, salva tokens renovados e grava eventos. Ações no jogo só saem por plugins ligados na conta **e** com `ACTION_MODE=enabled`. Com `observe_only` (o padrão), toda ação é recusada e registrada como `action.blocked`, o que serve para conferir as decisões de um plugin sem risco.

## Instalação

```bash
cd worker
uv venv --python 3.12
uv pip install -e ".[dev]"
cp ../.env.example .env   # preencha
```

## Rodando sem Supabase (modo memória)

Preencha `ACCOUNT_1_NICK`, `ACCOUNT_1_TOKEN` e `ACCOUNT_1_DEVICE_ID` no `.env` (o passo a passo para extrair está em [../docs/protocolo.md](../docs/protocolo.md)) e rode:

```bash
.venv/bin/pokeidle-farm run
```

Nesse modo os eventos ficam só em memória e no log. Serve para validar o handshake.

## Rodando com Supabase

1. Aplique a migration em `../supabase/migrations/` (pela Supabase CLI, com `supabase db push`, ou colando o SQL no editor).
2. Cadastre a conta no SQL editor:
   ```sql
   insert into public.accounts (owner_id, nick, role)
   values ('<seu auth.users.id>', '<nick>', 'farm');
   ```
3. Preencha `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` no `.env`.
4. Grave o token no Vault. Ele é pedido sem aparecer na tela:
   ```bash
   .venv/bin/pokeidle-farm set-token --nick <nick> --device <id-dispositivo>
   ```
5. `.venv/bin/pokeidle-farm run`

## Ligando um plugin que age no jogo

Plugins que não são `always_on` (hoje, o `restock` e o `rank`) só sobem se estiverem ligados na tabela `strategy_configs`:

```sql
insert into public.strategy_configs (account_id, plugin, enabled, config)
select id, 'restock', true, '{"items": [{"id": 200, "min": 50, "target": 100}]}'
  from public.accounts where nick = '<nick>';
```

Pelo painel é mais simples: **conta → Plugins**, que manda um comando `plugin.set`. O worker valida a config,
grava em `strategy_configs` e reinicia só aquele plugin, sem derrubar a sessão. Mudando direto no SQL, a config
só é lida quando a sessão fica `READY` (reinicie com `docker compose restart`).
Config inválida desliga o plugin (aparece no log). Os campos do `restock` estão na seção 7 do design.

O `rank` (fase 3b) tem um ensaio próprio, independente do `ACTION_MODE`: com `dry_run: true` (o padrão) ele
não manda `hunt.select` nem `auto.set` e grava `rank.would` com o que mandaria, além de um `rank.plan` (fila,
alvo, bola) a cada decisão. Isso existe porque o `ACTION_MODE` vale para o worker inteiro e o `restock` já roda
em `enabled`. A única mensagem que ele manda mesmo em `dry_run` é o `topcatch.pedir`, que só lê a lista de
espécies da semana. Para ensaiar numa conta: ligar o plugin `rank` com config `{}` e conferir na tabela
`events`:

```sql
select received_at, data->>'reason' as motivo, data->'target'->>'slug' as alvo,
       data->'target'->>'hours' as horas, data->>'ball_id' as bola, data->>'scored' as pontuadas
  from public.events where type = 'rank.plan' order by received_at desc limit 20;
```

Os campos da config estão em [../docs/design/fase-3b-plugin-rank.md](../docs/design/fase-3b-plugin-rank.md).

Para o `rank` agir de verdade (passo 5, [../docs/design/fase-3b-rank-ligado.md](../docs/design/fase-3b-rank-ligado.md)),
use o **Modo** da aba Agora da página da conta, que manda o comando `focus.set`: ele grava o `restock` com
`focus: "rank"` e o `rank` com `dry_run: false` de uma vez. O `rank` se recusa a agir (e continua gravando
`rank.would`) se o `restock` não estiver em `focus: "rank"`, porque os dois brigariam pelo `auto.set`. Agindo,
ele:

- manda o `hunt.select` só quando a trava de combate (`centroLivreEm`) e o `trocaLivreEm` passaram, no relógio do
  servidor; confirma pelo `hunt.changed`; com erro do jogo ou 15 s sem confirmação grava `rank.failed` e tenta de
  novo em 60 s (na 3ª falha seguida, pula a espécie); no máximo 10 trocas por hora;
- desliga a bola automática (ela exige VIP; [captura-manual.md](../docs/design/captura-manual.md)). **Gotcha:** por
  isso o `rank` hoje troca de hunt mas não joga bola; passar o alvo dele ao `ball_thrower` fica para quando voltar a
  ser usado;
- publica `rank.mode` (`active` com a bola, ou `fallback` quando a fila acaba). Em `fallback`, o `restock` age
  como o `fallback_focus` (ouro-xp-drop por padrão), então a conta nunca fica parada.

Na subida e depois de cada espécie que pontua, o `rank` também pede o ranking da semana (`ranking.pedir`, aba
`capturas`, só leitura, no máximo a cada 5 min) e grava `rank.position` com a posição calculada pela mesma regra
da tela do jogo, ou quantas espécies faltam para entrar no top 100. O card "Rank semanal" da página da conta mostra
isso junto com a fila (detalhes em [../docs/design/fase-3b-metricas-e-card.md](../docs/design/fase-3b-metricas-e-card.md)).

**Gotcha:** o padrão do `restock.focus` passou de `capture` para `gold_xp_drop` em 15/11. Uma conta com
`restock` sem `focus` na config para de jogar bola depois do rebuild; grave o modo pela aba Agora antes.

### Modo, desvio, treino e vigia (como se conectam)

Ver [docs/design/refatoracao-2026-11-20.md](../docs/design/refatoracao-2026-11-20.md).

- **Modo** (`focus.set`): XP (`gems` com `objective: "xp"`), Ouro e drop (só `restock`) ou Rank (`rank` + `restock`
  em `focus: "rank"`). Opções no mesmo comando: `catch_all` (o `restock` com `focus: "capture"`, a melhor bola que
  se paga em todo selvagem) e `train` (`{enabled, target_level}`, liga o `team_train`; fora do XP ele desliga).
- **Desvio**: `capture.start` (plugin `capture_target`) ou `hunt.select` (plugin `hunt_hold`). Começar um desliga o
  outro. Os dois seguram o `hunt.select` dos outros plugins por **travas** no `ActionGateway`: várias por ação, uma
  por dono; pedir a mesma hunt que um dono quer passa (é a volta do centro).
- **Treino**: o `team_train` escolhe quem treina (o mais fraco abaixo do alvo) e publica em `state.train_target`.
  O `gems` planeja a hunt para esse pokémon (hunts até o nível dele + `max_over_active`, padrão 10), e o
  `team_train` só troca o ativo quando a conta já está numa hunt segura para ele.
- **Vigia** (`watchdog`, sempre ligado): cura no centro, devolve o ativo depois da morte e, com 8 `battle.revive`
  em 3 min (o jogo revive em batalha e a conta nunca vai ao centro), marca o par (pokémon, hunt) como perigoso em
  `state.danger` por 6 h e volta o ativo para o mais forte. O `gems` e o `team_train` evitam os pares perigosos.
- **Confirmação pelo jogo**: os comandos do painel só ficam "feito" quando o efeito aparece. Algumas ações não mudam
  o estado na hora e o jogo só responde com um `batalha` (`k: "venda"` na venda do Depot, com `qtd` e `ganho`;
  `k: "colecao"` na marca de Coleção/Depot). A Coleção é a lista `automation.pokemonTravado`, não um campo do pokémon. A sessão guarda a última resposta de cada tipo (`session.replied`) e
  esses comandos se confirmam por ela; esperar o estado dava "sem confirmação" em ação feita (20/11).
- **Plano sem travar**: o `gems` usa só o que o simulador já tem em cache (por faixa de 10 níveis) e simula o resto
  numa thread fora do lock; quando termina, planeja de novo (`reason: "model_ready"`). O plano feito antes disso é
  gravado mas não troca de hunt: sem a previsão, as hunts altas saíam pelo nível e a conta trocava duas vezes.

Ordem segura para ligar algo novo: primeiro com `ACTION_MODE=observe_only`, conferindo os `action.blocked`
na tabela `events`; depois `ACTION_MODE=enabled` (com "d") e `docker compose up -d --force-recreate`, porque
o `restart` não relê o `.env`.

## Comandos do painel

O `run` também atende os comandos criados no painel (tabela `commands`, fase 4b): **Ping**, **Ligar/Desligar**
conta, **Reconectar** e **Configurar plugin**. O worker busca os pendentes a cada `COMMANDS_POLL_S` (5 s);
um comando que ninguém pega em 5 min expira. O processo fica no ar mesmo com todas as sessões paradas
(desligadas, `needs_login`), para poder religá-las por comando. Depois de gravar um token novo com `set-token`,
**Reconectar** sobe a sessão de novo sem reiniciar o Docker.

Para testar o caminho todo sem conectar no jogo (no codespace, por exemplo):

```bash
.venv/bin/pokeidle-farm listen --fake
```

As sessões ficam "prontas" de mentira; clique **Ping** no painel e o comando deve voltar `feito` em até 5 s.
Não rode o `listen --fake` ao mesmo tempo que o `run` de verdade: os dois pegariam os mesmos comandos.

## Simulador (desenvolver sem o jogo)

Grava eventos simulados, mas realistas, no banco: abates, drops, capturas com potência, qualidade e IV sorteados pelas tabelas dos Termos, trocas de hunt e quedas. Serve para desenvolver métricas e painel antes de o worker rodar contra o jogo.

```bash
.venv/bin/pokeidle-farm simulate --nick <nick> --days 3          # histórico dos últimos 3 dias
.venv/bin/pokeidle-farm simulate --nick <nick> --days 1 --live   # e continua gerando ao vivo
```

Os eventos simulados ficam marcados com `raw._sim = true`. Para apagar:

```sql
delete from public.events where raw->>'_sim' = 'true';
```

O ritmo (abates por minuto, chance de captura, drops) é um **chute** em `sim/generator.py`, não uma medição do jogo.

### No GitHub Codespaces

O repo tem um `.devcontainer/` que já abre com Python 3.12 e o worker instalado.

1. Cadastre os secrets `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` em **GitHub → Settings → Codespaces → Secrets**, liberando o repo `pokeidle-farm`. Eles viram variáveis de ambiente; não precisa de `.env`.
2. No repo: **Code → Codespaces → Create codespace on main** (máquina de 2 núcleos).
3. No terminal: `pokeidle-farm simulate --nick <nick> --days 3`.

Use o codespace só para desenvolver e simular. **Não rode `pokeidle-farm run` daqui**: é IP de datacenter, que o jogo bloqueia, e os termos do GitHub não permitem esse uso (ver [ADR 0011](../docs/decisions/0011-worker-em-ip-residencial.md)).

## Testes

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
```

Os testes usam um servidor WebSocket falso que imita o jogo (handshake, renovação de token, erros, close 4001, quedas), então não precisam do pokeidle.io nem do Supabase.

O projeto exige Python 3.12 (`>=3.12,<3.13`). Numa máquina sem ele (ex.: só com o 3.13), rode no Docker, a
partir da raiz do repo (no Git Bash do Windows, o `MSYS_NO_PATHCONV=1` evita que `/src` vire caminho do Windows):

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W)/worker:/src" python:3.12-slim   sh -c "cp -r /src /w && cd /w && pip install -q -e '.[dev]' && python -m pytest -q && ruff check ."
```

**Gotcha:** os plugins são achados pelos *entry points* do pacote. Rodando os testes só com as dependências
instaladas (sem o pacote), os comandos falham com "plugin desconhecido" e parte da suíte fica esperando. Para iterar
rápido, deixe um container de pé e instale o pacote uma vez (a suíte roda em ~13 s):

```bash
MSYS_NO_PATHCONV=1 docker run -d --name pf-test -v "$(pwd -W)/worker:/src" -w /src -e PYTHONPATH=/src/src python:3.12-slim sleep infinity
MSYS_NO_PATHCONV=1 docker exec pf-test sh -c "cp -r /src /tmp/w && pip install -q '/tmp/w[dev]' pytest-timeout"
MSYS_NO_PATHCONV=1 docker exec pf-test sh -c "python -m pytest -q --timeout=60 && ruff check src tests && ruff format --check src tests"
```

## Dados do jogo (fase 3b)

- **Catálogo de hunts**: vem no `welcome` (hunts, tabela `captura`, `catalogoBolas`). A sessão monta um
  `HuntCatalog` a cada conexão (`ctx.catalog` nos plugins) e grava em `game_hunts`/`game_catalog` só quando a
  versão muda.
- **Pokedex**: o `welcome` não traz o estágio evolutivo, então o worker baixa os `creatures*.json` públicos de
  `https://pokeidle.io/assets/` (o mesmo que o navegador baixa) na subida e a cada 24 h, com GET condicional
  por `ETag`: só baixa de novo quando o jogo atualiza. Vai para `ctx.species` e para `game_species`. Se a busca
  falhar, o worker segue com a última Pokedex gravada (aparece `species.fetch_failed` no log).
- Detalhes em [../docs/design/fase-3b-catalogo-e-fila.md](../docs/design/fase-3b-catalogo-e-fila.md).

## Estrutura

| Módulo | O que faz |
|---|---|
| `protocol/` | modelos e codec das mensagens do jogo; o único lugar que conhece o formato delas |
| `events.py` | eventos internos e o tradutor protocolo → evento |
| `bus.py` | barramento assíncrono com fila por assinante |
| `actions.py` | `ActionGateway` e `RateLimiter`; ações com schema Pydantic (`ShopBuy`, `AutoSet`, `TopCatchRequest`, `RankingRequest`, `HuntSelect`) |
| `catalog.py` | preços da loja do NPC (bolas, poções, revives) e chance das bolas |
| `pace.py` | ritmo de abates por hunt aprendido na sessão, projetado para o nível do pokémon (para baixo também); hunt não medida usa a previsão do simulador (`model/`) e, sem ela, o nível medido mais próximo (rank e gems) |
| `model/` | simulador do jogo (não confundir com `sim/`, que gera eventos falsos): `combat.py` prevê abates/h de um pokémon numa hunt com as regras do jogo; `predict.py` aplica ao pokémon planejado, com cache por faixa de 10 níveis; `progression.py` simula nível a nível até um marco (hunt, evoluções,
poções, ouro, bônus de XP até expirarem); `capture.py` é a sorte da captura (chance por bola, nascimento sorteado, Monte Carlo contra o ativo; ver [docs/design/simulador-3-captura.md](../docs/design/simulador-3-captura.md)). Ver [docs/design/simulador-1-combate.md](../docs/design/simulador-1-combate.md) |
| `gems_model.py` | valor em gemas de cada hunt: pedra do tipo a 0,2/0,35/0,5% por abate e teto de liquidez |
| `progress.py` | `Progress` do foco XP: grava o plano até o nível 150 (`progress.plan`) e evolui o ativo (`pokemon.evoluir`); ver [docs/design/simulador-2-progressao.md](../docs/design/simulador-2-progressao.md) |
| `hunt_switch.py` | `HuntSwitcher`: troca de hunt com trava, timer, confirmação e nova tentativa (gems, hunt_hold, capture_target) |
| `gamedata.py` | catálogo de hunts do `welcome`, Pokedex com estágio evolutivo e `SpeciesSync` (fase 3b); catálogo de itens (`ItemsSync`, `items.json` por ETag, e `itensNossos` do `welcome`; fase 7); wiki e fórmulas do jogo (`GameFilesSync`, em `game_files`) |
| `rank_queue.py` | fila de hunts do foco rank por tempo esperado até a captura (funções puras) |
| `session.py` | `AccountSession`: handshake, heartbeat, reconexão, lease, renovação de token. **Gotcha:** o Supabase derruba a conexão HTTP/2 de tempos em tempos (`RemoteProtocolError ... ConnectionTerminated`); qualquer erro inesperado reconecta com backoff e a renovação do lease só avisa no log. Antes, um erro desses encerrava a sessão e ninguém a subia (conta 2, 21/11) |
| `plugins/` | interface, registry (entry points), `telemetry` (grava os eventos), `restock` (fase 3a, ver [docs/design/fase-3-reposicao.md](../docs/design/fase-3-reposicao.md)), `gems` (focos gemas e XP, ver [docs/design/foco-xp.md](../docs/design/foco-xp.md) e [docs/design/foco-gemas-e-ritmo.md](../docs/design/foco-gemas-e-ritmo.md)), `daily` (passe de batalha grátis, resgate diário; ver [docs/design/simulador-4-decisoes.md](../docs/design/simulador-4-decisoes.md)), `seller` (fase 9, venda de pedras, em ensaio; ver [docs/design/fase-9-venda-de-pedras.md](../docs/design/fase-9-venda-de-pedras.md)), `market_prices` (fase 7, sempre ligado: pede as médias do Mercado a cada hora numa conta só e grava em `market_prices`; ver [docs/design/fase-7-precos-do-mercado.md](../docs/design/fase-7-precos-do-mercado.md)) `rank` (fase 3b, ver [docs/design/fase-3b-plugin-rank.md](../docs/design/fase-3b-plugin-rank.md) e [fase-3b-rank-ligado.md](../docs/design/fase-3b-rank-ligado.md)), `team_train` (treina a equipe), `watchdog` (vigia), `hunt_hold` (hunt manual) e `capture_target` (captura de uma espécie); os quatro últimos em [docs/design/refatoracao-2026-11-20.md](../docs/design/refatoracao-2026-11-20.md); `ball_thrower` (sempre ligado: joga `ball.throw` em todo shiny e nos corpos da captura ativa, ver [docs/design/captura-manual.md](../docs/design/captura-manual.md)) e `outland_tier` (sempre ligado: põe a conta no maior tier da Outland que o nível libera, porque o jogo não sobe sozinho; `active: false` para escolher à mão) e `notifier` (sempre ligado: avisos no Discord pelo `DISCORD_WEBHOOK_URL`, com um interruptor por tipo na config e um limite por minuto somando as contas; sem a URL fica degradado; `active: false` desliga os avisos da conta), `protect` (sempre ligado: põe na Coleção do jogo os shiny e os protegidos no painel; os comandos de Depot/Coleção recusam mandar protegido para o Depot) e `boss` (desligado por padrão, começa em ensaio: luta no boss do prêmio escolhido enquanto houver token); os dois em [docs/design/protegidos-e-bosses.md](../docs/design/protegidos-e-bosses.md) |
| `store/` | interface `Store`, implementação em memória e no Supabase |
| `sim/` | sorteios dos Termos (`rolls.py`) e gerador de eventos simulados |
| `commands.py` | `Supervisor` (sessões de todas as contas de farm) e `CommandLoop` (comandos do painel, fase 4b): sessão, `plugin.set`, `focus.set`, hunt e captura, equipe (`team.*`), Coleção/Depot, loja (`shop.buy`) e Mercado (`market.sell`/`market.cancel`) chocadeira (`incubator.put`) e tier da Outland (`outland.tier`). Tipo novo de comando precisa também da migration que libera o tipo em `commands_type_check` |
| `main.py` | CLI (`run`, `listen --fake`, `set-token`, `simulate`) |
