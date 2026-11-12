# worker

Worker headless do pokeidle-farm. A visão geral, as decisões e o design estão em [../README.md](../README.md) e [../docs/](../docs/). O design desta fase está em [../docs/design/fase-2.md](../docs/design/fase-2.md).

> Fase 2: o worker **só observa**. Ele conecta, mantém a sessão, salva tokens renovados e grava eventos. Nenhuma ação é enviada ao jogo (`ACTION_MODE=observe_only`).

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
| `actions.py` | `ActionGateway` e `RateLimiter`; ações com schema Pydantic |
| `session.py` | `AccountSession`: handshake, heartbeat, reconexão, lease, renovação de token |
| `plugins/` | interface, registry (entry points) e o plugin `telemetry` |
| `store/` | interface `Store`, implementação em memória e no Supabase |
| `sim/` | sorteios dos Termos (`rolls.py`) e gerador de eventos simulados |
| `main.py` | CLI (`run`, `set-token`, `simulate`) |
