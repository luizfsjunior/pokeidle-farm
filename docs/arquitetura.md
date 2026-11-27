# Arquitetura

## Objetivo

Manter 3 contas de farm rodando 24/7 de forma headless, com um painel web para acompanhar o estado, mudar estratégias e medir se o farm compensa financeiramente.

## Componentes

### 1. Worker (`worker/`)

Python 3.12 com asyncio, `websockets` e Pydantic. Roda em Docker numa máquina com IP residencial (o jogo recusa
IP de datacenter, [ADR 0011](decisions/0011-worker-em-ip-residencial.md)); hoje, o PC de casa.

| Módulo | Responsabilidade |
|---|---|
| `AccountSession` | Uma por conta. Faz a conexão WebSocket, o handshake com o token, o heartbeat e a reconexão com backoff exponencial. |
| `protocol` | Modelos Pydantic das mensagens do jogo (entrada e saída). Nada de JSON solto fora daqui. |
| `events` | `Translator`: traduz as mensagens do jogo em eventos tipados (abate, drop, captura, estado, troca de hunt, Top Catch, ranking, médias do Mercado). A sessão publica no barramento (`bus`); os plugins assinam. |
| `plugins/` | Plugins com interface comum (`Plugin`, `PluginContext`), ligados e configurados por conta em `strategy_configs`: `telemetry`, `market_prices` e `notifier` (avisos no Discord) sempre ligados, `restock`, `rank`, `gems` e `seller`. Ver [ADR 0008](decisions/0008-escopo-completo-modular.md) e os desenhos em `design/`. |
| `actions` | `ActionGateway`: único caminho para mandar ações ao jogo (`ShopBuy`, `AutoSet`, `HuntSelect`, `TopCatchRequest`, `RankingRequest`, `MarketAverages`), com o `ACTION_MODE` e um `RateLimiter` por ação e conta, para cumprir o "não sobrecarregar o servidor". |
| `gamedata` | Catálogo de hunts (do `welcome`), Pokedex e itens (dos JSON públicos do jogo, por ETag), gravados no banco só quando mudam. |
| `commands` | `Supervisor` (sessões de todas as contas) e `CommandLoop`: busca os comandos pendentes do painel a cada `COMMANDS_POLL_S` (5 s) e executa um por vez. |

Princípios:
- Toda a configuração vem de variáveis de ambiente, para a mesma imagem rodar em qualquer máquina.
- Nenhuma porta é exposta: o worker só abre conexões de saída (para o jogo e para o Supabase).
- Estado e histórico ficam no banco, não no processo. Trocar o lugar onde o worker roda não perde nada.

### 2. Banco (`supabase/`)

Postgres no Supabase, com RLS ligada em todas as tabelas.

| Tabela | Conteúdo |
|---|---|
| `accounts` | nick, papel (`farm` ou `personal`), ativa |
| `account_tokens` | token de sessão (no Vault), com o dispositivo |
| `account_leases` | qual worker está com cada conta (evita duas sessões na mesma conta) |
| `commands` | comandos do painel (ligar, desligar, reconectar, `plugin.set`, `focus.set`), com status |
| `events` | eventos brutos e imutáveis (drops, capturas, shinies, mortes, desconexões), a fonte da verdade |
| `metric_hourly` | agregados por hora, conta, hunt e métrica base, recalculáveis a partir de `events` |
| `metric_daily` | view: os mesmos agregados por dia (fuso de Brasília) |
| `metric_definitions` | métricas base (soma) e razões (numerador ÷ denominador), declarativas |
| `goals` | objetivos de métrica (somar até um alvo) ou de captura (N pokémon que batem com um filtro), com prazo e contas |
| `goal_snapshots` | progresso de hora em hora de cada objetivo (valor atual, ritmo, previsão, chance até o prazo) |
| `market_asks` | menor anúncio aberto, unidades nele e a fila de cada pedra, de hora em hora (o preço de venda real) |
| `market_prices` | médias de 7 dias do Mercado por item e moeda, um snapshot por hora (30 dias), para dar valor aos drops |
| `game_files` | wiki (`pokepedia.mjs`) e módulos de fórmulas do jogo, como vieram (só no banco; o repositório é público) |
| `game_hunts`, `game_species`, `game_items`, `game_catalog` | dados do jogo: hunts, Pokedex com estágio evolutivo, itens com preço de NPC e a versão de cada um |
| `evaluation_settings` | parâmetros do custo de energia para o "Compensa?" |
| `strategy_configs` | quais plugins estão ligados por conta, e com quais parâmetros |

### Camadas de métricas

```
events (brutos, imutáveis)
   └─> metric_hourly → metric_daily (agregados recalculáveis; pg_cron a cada 10 min)
          └─> metric_definitions (base e razões, declarativas) → metric_series()
                 └─> goals → goal_progress() → goal_snapshots (de hora em hora)
```

Uma razão nova é só uma linha em `metric_definitions`. Uma métrica base nova é uma linha ali e uma coluna no `refresh_metric_hourly`. Se a definição mudar, o histórico é recalculado a partir dos eventos brutos. Detalhes e fórmulas da previsão: [ADR 0012](decisions/0012-metricas-em-camadas.md).

### 3. Painel (`web/`)

Next.js na Vercel, com Supabase Auth por e-mail e senha (Google pode entrar depois, sem mudar o RLS), só a chave pública e RLS restrita ao dono. Código em `web/`.

- Visão geral: status de cada conta, números do dia por hora ativa (inclusive o valor dos drops) e a linha do rank
- Página da conta: comandos (ligar, desligar, reconectar), foco (captura, ouro-xp-drop, rank), card do rank e os
  plugins em JSON
- Métricas em gráfico e objetivos com progresso e previsão
- `/hunts` (o que cada hunt rendeu) e `/economia` (vendas, drops pelo preço do Mercado e o "compensa?": renda em US$
  contra o custo; pedras não contam como renda, docs/design/painel-ux-v2.md)
- Aviso de token expirado (status `needs_login`)

## Fluxos

**Comando do painel:** o painel grava em `commands` → o worker pega os pendentes a cada 5 s (`claim_commands`, atômico) → executa (ex.: `focus.set` grava `restock` e `rank` e reinicia os dois) → grava o resultado com `finish_command` → o painel acompanha o status.

**Telemetria:** a sessão recebe um evento do jogo → `Telemetry` grava em `events` → o pg_cron agrega em `metric_hourly` a cada 10 minutos.

**Ação de um plugin:** um plugin (ex.: `restock`) recebe eventos → decide → `ActionGateway.submit` → o gateway recusa se `ACTION_MODE=observe_only` ou se o RateLimiter barrar, e senão manda ao jogo → tudo vira `action.sent`/`action.blocked` em `events`. A confirmação vem pelo `estado` seguinte (estoque, `automation`), não por uma resposta própria.

**Token expirado:** o handshake falha → a conta é marcada como `needs_login` → o painel avisa → você faz o login no navegador e atualiza o token.

## Questões em aberto

- Mensagens WebSocket ainda não confirmadas (ver as pendências em [protocolo.md](protocolo.md)): falta só ver um
  `sessao.renovada`.
- Quanto tempo dura o token de sessão.
- RAM com 3 sessões: com uma, o container usa ~60 MB (15/11); a VM do WSL tem teto de 2 GB.
