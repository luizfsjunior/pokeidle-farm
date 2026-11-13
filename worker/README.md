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

Plugins que não são `always_on` (hoje, o `restock`) só sobem se estiverem ligados na tabela `strategy_configs`:

```sql
insert into public.strategy_configs (account_id, plugin, enabled, config)
select id, 'restock', true, '{"items": [{"id": 200, "min": 50, "target": 100}]}'
  from public.accounts where nick = '<nick>';
```

Pelo painel é mais simples: **conta → Plugins**, que manda um comando `plugin.set`. O worker valida a config,
grava em `strategy_configs` e reinicia só aquele plugin, sem derrubar a sessão. Mudando direto no SQL, a config
só é lida quando a sessão fica `READY` (reinicie com `docker compose restart`).
Config inválida desliga o plugin (aparece no log). Os campos do `restock` estão na seção 7 do design.

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

## Estrutura

| Módulo | O que faz |
|---|---|
| `protocol/` | modelos e codec das mensagens do jogo; o único lugar que conhece o formato delas |
| `events.py` | eventos internos e o tradutor protocolo → evento |
| `bus.py` | barramento assíncrono com fila por assinante |
| `actions.py` | `ActionGateway` e `RateLimiter`; ações com schema Pydantic (`ShopBuy`, `AutoSet`) |
| `catalog.py` | preços da loja do NPC (bolas, poções, revives) e chance das bolas |
| `session.py` | `AccountSession`: handshake, heartbeat, reconexão, lease, renovação de token |
| `plugins/` | interface, registry (entry points), `telemetry` (grava os eventos) e `restock` (fase 3a, ver [docs/design/fase-3-reposicao.md](../docs/design/fase-3-reposicao.md)) |
| `store/` | interface `Store`, implementação em memória e no Supabase |
| `sim/` | sorteios dos Termos (`rolls.py`) e gerador de eventos simulados |
| `commands.py` | `Supervisor` (sessões de todas as contas de farm) e `CommandLoop` (comandos do painel, fase 4b) |
| `main.py` | CLI (`run`, `listen --fake`, `set-token`, `simulate`) |
