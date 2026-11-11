# Arquitetura

## Objetivo

Manter 3 contas de farm rodando 24/7 de forma headless, com um painel web para acompanhar o estado, mudar estratégias e medir se o farm compensa financeiramente.

## Componentes

### 1. Worker (`worker/`)

Python 3.12 com asyncio, `websockets` e Pydantic. Roda em Docker, na máquina local ou num droplet.

| Módulo | Responsabilidade |
|---|---|
| `AccountSession` | Uma por conta. Faz a conexão WebSocket, o handshake com o token, o heartbeat e a reconexão com backoff exponencial. |
| `protocol` | Modelos Pydantic das mensagens do jogo (entrada e saída). Nada de JSON solto fora daqui. |
| `strategies` | Módulos plugáveis, ligáveis pelo painel: melhor hunt, reposição de bolas/poções/revives, venda de sobras. |
| `RateLimiter` | Intervalo mínimo por tipo de ação e por conta, para cumprir o "não sobrecarregar o servidor". |
| `Telemetry` | Grava eventos (drops, capturas, XP, gold, quedas de conexão) no Supabase. |
| `CommandListener` | Assina a tabela `commands` via Supabase Realtime e despacha para a sessão certa. |

Princípios:
- Toda a configuração vem de variáveis de ambiente, para a mesma imagem rodar local ou no VPS.
- Nenhuma porta é exposta: o worker só abre conexões de saída (para o jogo e para o Supabase).
- Estado e histórico ficam no banco, não no processo. Trocar o lugar onde o worker roda não perde nada.

### 2. Banco (`supabase/`)

Postgres no Supabase, com RLS ligada em todas as tabelas.

| Tabela | Conteúdo |
|---|---|
| `accounts` | nick, papel (`farm` ou `personal`), ativa |
| `account_tokens` | token de sessão criptografado, data de expiração |
| `commands` | comandos do painel (ex.: trocar hunt, pausar), com status |
| `account_state` | último estado de cada conta (nível, hunt, gold, inventário resumido) |
| `events` | drops, capturas, shinies, mortes, desconexões |
| `metrics_hourly` | agregados por hora e por conta (XP/h, gold/h, drops) |
| `market_prices` | preços observados no Mercado, para dar valor aos drops |

### 3. Painel (`web/`)

Next.js na Vercel, com Supabase Auth via Google e RLS restrita ao dono.

- Status em tempo real das contas (online, hunt atual, XP/h)
- Controles: pausar, retomar, trocar estratégia
- Gráficos de drops e "valor estimado em Gemas por dia"
- Aviso de token expirado

## Fluxos

**Comando do painel:** o painel grava em `commands` → o Realtime avisa o worker → o worker executa respeitando o RateLimiter → atualiza o status do comando e o `account_state`.

**Telemetria:** a sessão recebe um evento do jogo → `Telemetry` grava em `events` → um job agrega em `metrics_hourly`.

**Token expirado:** o handshake falha → a conta é marcada como `needs_login` → o painel avisa → você faz o login no navegador e atualiza o token.

## Questões em aberto

- Formato do handshake e das mensagens WebSocket (ver [protocolo.md](protocolo.md)).
- Quanto tempo dura o token de sessão.
- Quantos MB de RAM as 3 sessões usam de fato (512 MB bastam?).
