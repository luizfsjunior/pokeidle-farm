# Design — Fase 2: núcleo do worker

- **Status:** Revisado (2026-11-12)
- **Data:** 2026-11-12
- **Relacionado:** [ADR 0002](../decisions/0002-worker-headless-websocket.md), [0003](../decisions/0003-supabase-como-intermediario.md), [0005](../decisions/0005-auth-por-token-de-sessao.md), [0008](../decisions/0008-escopo-completo-modular.md), [0010](../decisions/0010-supabase-desde-o-inicio.md)

## Premissa

> ⚠️ O handshake e as mensagens seguem o mapeamento do DiuleJR/pokeidle-manager-online ([protocolo.md](../protocolo.md)), **ainda não confirmado por nós no DevTools**. O design isola o protocolo num único módulo (`protocol/`) para que uma correção futura não se espalhe pelo código.

## Objetivo da fase

Uma conta conectada, **só escutando**: o worker faz o handshake, mantém a sessão, salva os tokens renovados e grava todos os eventos brutos no Supabase. Nenhuma ação de jogo é enviada.

Ao final, já devem existir:
- a interface de plugin, com um único plugin de exemplo (`telemetry`);
- o barramento de eventos;
- o schema inicial do Supabase com RLS.

## Estrutura

```
worker/
├─ pyproject.toml
└─ src/pokeidle_farm/
   ├─ main.py              # sobe as sessões a partir do banco/.env
   ├─ config.py            # pydantic-settings, lê o .env
   ├─ protocol/
   │  ├─ messages.py       # modelos Pydantic das mensagens do jogo
   │  └─ codec.py          # JSON ↔ modelos; mensagem desconhecida vira UnknownMessage
   ├─ session.py           # AccountSession: conexão, hello, heartbeat, reconexão
   ├─ bus.py               # EventBus (pub/sub assíncrono)
   ├─ events.py            # eventos internos tipados
   ├─ actions.py           # ActionGateway + RateLimiter (na fase 2, bloqueia tudo)
   ├─ plugins/
   │  ├─ base.py           # interface Plugin
   │  ├─ registry.py       # descoberta e ciclo de vida dos plugins
   │  └─ telemetry.py      # grava eventos brutos no Supabase
   └─ store/
      └─ supabase.py       # acesso ao banco (eventos, tokens, estado)
```

## 1. Eventos internos

### Princípios

- **Duas camadas:** a *mensagem do jogo* (formato do servidor, em `protocol/`) e o *evento interno* (formato nosso, em `events.py`). Plugins só veem eventos internos, então se o protocolo mudar, só o `codec` muda.
- **Nada se perde:** todo evento interno carrega o `raw` (o JSON original). Campos que ainda não modelamos ficam disponíveis para métricas futuras.
- **Imutáveis e com horário do servidor:** cada evento tem `server_ts` (do relógio do servidor, via o offset calculado a partir de `estado.servidorAgora`) e `received_at` (relógio local).

### Envelope comum

```python
class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID                    # gerado no worker
    account_id: UUID
    type: str                   # ex.: "kill", "capture_attempt"
    server_ts: datetime | None  # relógio do servidor (corrigido pelo offset)
    received_at: datetime       # relógio local
    session_id: UUID            # uma por conexão; ajuda a separar quedas
    raw: dict[str, Any]         # mensagem original do jogo
```

### Tipos da fase 2

| `type` | Origem (protocolo) | Campos tipados | Uso em métricas |
|---|---|---|---|
| `session.connected` | `welcome` | `level`, `hunt_slug`, `server_offset_ms` | uptime |
| `session.disconnected` | close / erro | `code`, `reason`, `will_retry` | uptime, estabilidade |
| `session.rejected` | `erro` com `auth.*` / `login.*` | `key`, `ban_reason?` | alertas |
| `session.token_renewed` | `sessao.renovada` | — (o token **não** vai para o evento) | auditoria |
| `state.snapshot` | `welcome.estado` | `level`, `hunt_slug`, `items`, `active_pokemon_id` | estado inicial de cada sessão |
| `state.patch` | `estado` | `changed` (dict), `pokemon_changed`, `pokemon_removed` | evolução do inventário |
| `hunt.changed` | `batalha` / `k: hunt` | `slug`, `name` | tempo por hunt |
| `kill` | `batalha` / `k: morte` | `wild_name`, `xp`, `gold`, `gold_autosell`, `drops: list[Drop]` | XP/h, gold/h, drops/h |
| `capture_attempt` | `batalha` / `k: bola` | `ball_id`, `success`, `shiny`, `chance` | taxa de captura |
| `wild_fled` | `batalha` / `k: fugiu` | `name`, `level` | perdas |
| `pokecenter` | `batalha` / `k: centro` | `reason` | tempo parado |
| `unknown` | qualquer outro | — | descobrir mensagens novas |

`Drop` começa só com `name` (o único campo confirmado na referência), mais `raw`. Ele ganha campos quando conferirmos o formato no DevTools.

Os eventos de ataque (`k: ataque`) **não** são gravados: são muitos e não alimentam nenhuma métrica planejada. Eles ainda passam pelo barramento, caso algum plugin precise.

### Barramento

```python
class EventBus:
    def subscribe(self, types: set[str] | Literal["*"], handler: Handler) -> Unsubscribe: ...
    async def publish(self, event: Event) -> None: ...
```

- Cada assinante tem uma fila própria (`asyncio.Queue`, limitada). Um plugin lento não trava os outros nem a sessão.
- Se a fila de um assinante encher, os eventos mais antigos desse assinante são descartados e o descarte é registrado em log. O plugin de telemetria tem fila maior e grava em lote.
- Exceções num handler são isoladas e registradas, e o plugin é marcado como `degraded` sem derrubar a sessão.

## 2. Interface de plugin

```python
class PluginContext(Protocol):
    account_id: UUID
    config: BaseModel                         # config validada do plugin, por conta
    bus: EventBus
    actions: ActionGateway                    # único caminho para mandar ações
    state: AccountStateView                   # leitura do último estado conhecido
    store: PluginStore                        # chave-valor próprio do plugin, persistido
    log: Logger

class Plugin(ABC):
    name: ClassVar[str]                       # ex.: "telemetry", "hunt.best"
    config_model: ClassVar[type[BaseModel]]   # schema da config (Pydantic)
    subscribes: ClassVar[set[str] | Literal["*"]]

    async def start(self, ctx: PluginContext) -> None: ...
    async def on_event(self, event: Event) -> None: ...
    async def stop(self) -> None: ...
```

Regras:
- **Plugins não falam com o WebSocket.** Toda ação passa pelo `ActionGateway`, que aplica o `RateLimiter`, as travas do jogo (combate, uma compra por vez) e registra a ação como evento (`action.sent`, `action.result`).
- **Na fase 2, o `ActionGateway` está em modo `observe_only`:** qualquer ação é recusada e registrada em log. Isso garante o "só escutando".
- **A config é validada com Pydantic** a partir da tabela `strategy_configs`. Config inválida desliga o plugin e mostra o erro no painel, em vez de derrubar o worker.
- **Ciclo de vida:** o `registry` sobe os plugins ligados quando a sessão recebe o `welcome`, e os para quando a sessão cai ou recebe o comando de desligar.
- **Ações descritas por schema:** cada ação do `ActionGateway` (trocar hunt, comprar, anunciar...) tem um modelo Pydantic de entrada e um de resultado, com descrição. Isso deixa o terreno pronto para expor as ações como *tools* de um agente no futuro (ver [roadmap](../roadmap.md), "Ideias futuras"), sem retrabalho.
- **Descoberta:** entry points do Python (`[project.entry-points."pokeidle_farm.plugins"]`). Plugin novo é um módulo e uma linha no `pyproject.toml`, sem mexer no núcleo.

### Plugin da fase 2: `telemetry`

- Assina `*` menos os eventos de ataque.
- Junta eventos em lotes (até 100 eventos ou 2 s) e grava em `events`.
- Se o Supabase falhar, guarda num buffer local em disco (JSONL) e reenvia depois, para não perder evento por queda de rede.

## 3. Sessão

```
DISCONNECTED → CONNECTING → HANDSHAKING → READY → (DISCONNECTED | REJECTED | NEEDS_LOGIN)
```

| Situação | Comportamento |
|---|---|
| `welcome` em até 15 s | `READY`; calcula o offset do relógio; sobe os plugins |
| Queda de rede | backoff exponencial de 10 s a 5 min, com jitter |
| `auth.sessaoInvalida`, `auth.precisaLogin`, HTTP 401/403 | `NEEDS_LOGIN`, **não reconecta**; avisa o painel |
| Close 4001 (login externo) | `NEEDS_LOGIN`: alguém abriu a conta em outro lugar |
| `auth.contaBanida`, `auth.ipBanido`, `auth.provedorBanido` | `REJECTED`, para a conta; alerta |
| `login.limiteOnlineIp*` | espera 30 s e tenta de novo, no máximo N vezes |
| `sessao.renovada` | grava o token novo em `account_tokens` **antes** de qualquer outra coisa |

O heartbeat usa o ping do WebSocket a cada 30 s, e a conexão é dada como morta sem pong em 90 s.

## 4. Schema inicial do Supabase

Arquivo: [`supabase/migrations/20261112000000_init.sql`](../../supabase/migrations/20261112000000_init.sql) (nome no formato da Supabase CLI). Validado num Postgres 16 local com stubs do Vault e do auth: token, lease e RLS se comportam como esperado.

```sql
create table accounts (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users(id),
  nick        text not null unique,
  role        text not null check (role in ('farm', 'personal')),
  enabled     boolean not null default true,
  status      text not null default 'offline'
              check (status in ('offline','connecting','ready','needs_login','rejected')),
  created_at  timestamptz not null default now()
);

-- Token no Supabase Vault; aqui fica só a referência ao segredo.
create table account_tokens (
  account_id      uuid primary key references accounts(id) on delete cascade,
  token_secret_id uuid not null,      -- id em vault.secrets
  device_id       text not null,
  renewed_at      timestamptz not null default now()
);

-- Lease: só uma instância do worker por conta ao mesmo tempo.
create table account_leases (
  account_id  uuid primary key references accounts(id) on delete cascade,
  holder      text not null,          -- ex.: "local-notebook", "droplet-1"
  expires_at  timestamptz not null    -- renovado a cada ~30 s pelo dono do lease
);

create table events (
  id          uuid primary key,
  account_id  uuid not null references accounts(id) on delete cascade,
  session_id  uuid not null,
  type        text not null,
  server_ts   timestamptz,
  received_at timestamptz not null,
  data        jsonb not null,         -- campos tipados do evento
  raw         jsonb not null          -- mensagem original
);
create index events_account_time on events (account_id, received_at desc);
create index events_type_time    on events (type, received_at desc);

create table strategy_configs (
  account_id  uuid not null references accounts(id) on delete cascade,
  plugin      text not null,
  enabled     boolean not null default false,
  config      jsonb not null default '{}',
  updated_at  timestamptz not null default now(),
  primary key (account_id, plugin)
);

-- RLS: o dono lê as próprias contas, eventos e configs; tokens só via service_role.
alter table accounts         enable row level security;
alter table account_tokens   enable row level security;  -- sem policies = só service_role
alter table account_leases   enable row level security;  -- sem policies = só service_role
alter table events           enable row level security;
alter table strategy_configs enable row level security;

create policy own_accounts on accounts
  for all using (owner_id = auth.uid());
create policy own_events on events
  for select using (account_id in (select id from accounts where owner_id = auth.uid()));
create policy own_configs on strategy_configs
  for all using (account_id in (select id from accounts where owner_id = auth.uid()));
```

### Token no Supabase Vault

O token fica criptografado no [Supabase Vault](https://supabase.com/docs/guides/database/vault). Qualquer worker que tenha a `SUPABASE_SERVICE_ROLE_KEY` (local, droplet, outro PC) pega o token atual, sem precisar logar de novo. E quando um worker recebe `sessao.renovada`, todos passam a usar o token novo.

Acesso só por funções `security definer`, executáveis apenas pela `service_role`:

```sql
-- grava/atualiza o token (cria ou atualiza o segredo no Vault)
create function set_account_token(p_account uuid, p_token text, p_device text) returns void ...
-- lê o token em texto (via vault.decrypted_secrets)
create function get_account_token(p_account uuid) returns table (token text, device_id text) ...

revoke all on function set_account_token, get_account_token from public, anon, authenticated;
grant execute on function set_account_token, get_account_token to service_role;
```

Consequência: a `service_role key` vira a chave-mestra. Quem tiver ela lê os tokens. Ela fica só no `.env` dos workers, nunca no painel nem na Vercel.

### Lease por conta

O mesmo token aberto em dois lugares derruba um deles (close 4001). Como agora o worker pode rodar em qualquer lugar, **duas instâncias não podem pegar a mesma conta**:
- Antes de conectar, o worker tenta pegar o lease da conta (`insert ... on conflict do update where expires_at < now()`).
- Quem tem o lease renova a cada ~30 s. Se o worker morrer, o lease expira em ~90 s e outra instância pode assumir.
- Sem lease, o worker não conecta a conta e registra que ela está com outro `holder`.

As tabelas `commands`, `account_state`, `metrics_hourly`, `metric_definitions`, `goals` e `goal_snapshots` ficam para as fases 3, 4 e 7.

### Volume de `events`

Estimativa grosseira: com uma conta abatendo a cada ~10 s, são ~8.600 eventos `kill` por dia. Com `raw` de ~1 KB, dá ~8–10 MB por dia por conta, ou **~1 GB por mês com 3 contas**. Isso estoura o plano grátis rápido. Mitigações, a decidir:
- não gravar `raw` dos tipos já bem modelados (só `data`);
- gravar `raw` só para `unknown` e por amostragem;
- mover eventos antigos para arquivo (Parquet no Storage) depois que os agregados forem calculados.

## Decisões tomadas na revisão (2026-11-12)

1. **Criptografia do token: Supabase Vault.** Permite rodar o worker em qualquer lugar sem relogar. Exige o lease por conta (ver acima).
2. **`raw`: guardar tudo por enquanto.** Revisar a política de armazenamento antes da fase 5.
3. **Python 3.12.**

## Critério de pronto

- [ ] O worker conecta 1 conta com token do `.env` e chega em `READY`
- [ ] Sobrevive a derrubar a rede local e volta sozinho
- [ ] Um `sessao.renovada` atualiza o token no banco (ou é simulado em teste)
- [ ] Eventos aparecem em `events` com `data` e `raw`
- [ ] Nenhuma ação é enviada ao jogo (teste garantindo o `observe_only`)
- [ ] Mensagens desconhecidas aparecem como `unknown`
- [ ] Uma segunda instância do worker não conecta uma conta cujo lease está com outra
- [ ] Token lido e gravado só pelo Vault, via `get_account_token` e `set_account_token`
