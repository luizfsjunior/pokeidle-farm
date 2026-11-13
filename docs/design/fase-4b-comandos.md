# Fase 4b — comandos do painel para o worker

Status: **implementado** em 13/11 (migration `20261113010000_commands.sql`, `worker/.../commands.py`, painel). Segue o [ADR 0003](../decisions/0003-supabase-como-intermediario.md):
o painel nunca fala direto com o worker; tudo passa pelo Supabase.

## Objetivo

Controlar as contas pelo painel, não só acompanhar: ligar e desligar uma conta, forçar
reconexão e ligar, desligar ou configurar plugins. Tudo testável com o simulador, sem o jogo.

## 1. Tabela `commands`

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid pk | `gen_random_uuid()` |
| `owner_id` | uuid | `default auth.uid()`, FK `auth.users` |
| `account_id` | uuid | FK `accounts`, `on delete cascade` |
| `type` | text | `check` com a lista da seção 3 |
| `params` | jsonb | `default '{}'` |
| `status` | text | `pending` → `running` → `done` / `failed`; ou `cancelled` / `expired` |
| `result` | jsonb | o que o worker quiser devolver |
| `error` | text | mensagem curta, sem token nem dado sensível |
| `holder` | text | qual instância do worker pegou (mesmo valor do lease) |
| `created_at`, `started_at`, `finished_at` | timestamptz | |
| `expires_at` | timestamptz | `default now() + interval '5 minutes'`: comando velho não roda de surpresa |

Índice: `(account_id, status, created_at)`.

**RLS**
- `authenticated`: `select` e `insert` só em contas próprias (`account_id in (select id from accounts where owner_id = auth.uid())`).
- Sem `update`/`delete` direto. Cancelar é pela função `cancel_command(id)` (invoker), que só passa de `pending` para `cancelled`.
- O worker usa a service_role.

**Realtime**: `alter publication supabase_realtime add table public.commands;` para o painel
ver o status mudando e o worker receber o INSERT.

## 2. Como o worker pega e executa

`claim_commands(p_account uuid, p_holder text) returns setof commands`, security definer, só service_role:

1. marca `expired` o que está `pending` com `expires_at < now()`;
2. `update ... set status = 'running', started_at = now(), holder = p_holder`
   nos `pending` da conta, em ordem de `created_at`, com `for update skip locked`;
3. devolve as linhas pegas.

`finish_command(p_id, p_status, p_result, p_error)`, também só service_role, fecha o comando.

No worker (`commands.py`):

- **Decidido na implementação: só polling**, `claim_commands` a cada `COMMANDS_POLL_S` (5 s) para todas as
  contas do worker numa chamada. Comando é raro e 5 s de espera não incomodam; evita depender do cliente
  Realtime assíncrono do `supabase-py`. O Realtime fica habilitado na tabela para o futuro.
- Um `Supervisor` cuida das sessões de todas as contas de farm, inclusive as desligadas (para `account.enable`).
  O processo não termina quando as sessões param: espera comandos.
- Um `CommandRouter` com handlers por `type`. `params` validado com Pydantic; tipo desconhecido
  ou params inválidos → `failed` com o motivo.
- Limite: no máximo 10 comandos por minuto por conta (o excedente fica `failed: rate_limited`).
- Cada execução vira também um evento `command.executed` em `events`, para a auditoria e as métricas.
- Se o worker morrer no meio, o comando fica `running`. Ao subir, `recover_commands(holder)` marca
  todos os `running` daquele `holder` como `failed: interrompido`. Não reexecuta sozinho.

## 3. Comandos da v1

| `type` | `params` | O que faz |
|---|---|---|
| `account.enable` | — | `accounts.enabled = true`; o worker abre a sessão |
| `account.disable` | — | fecha a sessão de forma limpa e `enabled = false` |
| `session.reconnect` | — | derruba e reconecta (útil depois de `needs_login` + token novo) |
| `plugin.set` | `{plugin, enabled?, config?}` | grava em `strategy_configs` e recarrega o plugin sem reiniciar |
| `ping` | — | responde `{latency_ms, state}`; serve para testar o caminho todo |

Depois (fase 3 em diante): `hunt.set`, `auto.set`, `pokecenter.go`. Esses mandam mensagem ao jogo
e passam pelo RateLimiter.

## 4. Painel

- No card da visão geral: botões **Ligar/Desligar**, **Reconectar** e **Ping**.
- Ao clicar: `insert` em `commands` e consulta da linha a cada 1,5 s até terminar. O botão mostra
  "na fila → executando → feito/falhou".
- Página `/comandos`: histórico (últimos 100) com status, quem pegou, duração e erro;
  botão **Cancelar** nos pendentes.
- Página da conta (nova): plugins com liga/desliga e a config em JSON (vira `plugin.set`).

## 5. Testes

- SQL (`supabase/tests/commands_test.sql`): RLS (outro usuário não vê nem cria), claim atômico
  (duas chamadas não pegam o mesmo comando), expiração, cancelamento só de `pending`.
- Worker (pytest): router com sessão falsa e `MemoryStore`; params inválidos; rate limit;
  recuperação de `running` órfão.
- Ponta a ponta sem o jogo: `pokeidle-farm listen --nick <nick> --fake` sobe só o loop de comandos
  com uma sessão simulada. Clicar **Ping** no painel deve voltar `done` em poucos segundos.

## 6. Retenção

pg_cron diário apaga comandos finalizados com mais de 30 dias.

## 7. Ordem de implementação

1. Migration `…_commands.sql` + `commands_test.sql`.
2. `commands.py` no worker (router, claim, Realtime + polling) + testes + `listen --fake`.
3. Botões e histórico no painel.
4. `plugin.set` e a página da conta.

## Em aberto

- Comandos para "todas as contas" de uma vez: por ora o painel insere um por conta.
- A lista de plugins disponíveis vem do worker (entry points); o painel ainda sugere só `restock`.
  Um `ping` poderia devolver a lista.
