# pokeidle-farm

Automação de farm para o [pokeidle.io](https://pokeidle.io), com um worker headless em Python e um painel web para acompanhar e controlar as contas.

> Projeto pessoal, sem vínculo com o pokeidle.io. Os Termos do jogo (seção 5, "Automação") permitem automações desde que sigam as mesmas regras de quem joga na mão: sem explorar falhas, sem burlar limites (contas por pessoa/rede, travas e retenções do Mercado) e sem sobrecarregar o servidor. Veja [docs/regras-do-jogo.md](docs/regras-do-jogo.md).

## Status

🟡 Em planejamento: arquitetura definida, protocolo ainda não mapeado.

## Visão geral

```
[Painel Next.js — Vercel] ──Supabase Auth (Google)──┐
                                                     ▼
                                        [Supabase: Postgres + Realtime]
                                                     ▲
                    lê comandos / grava estado e métricas
                                                     │
[Droplet DigitalOcean — Docker] worker Python (asyncio) ── WebSocket ──> pokeidle.io
   ├─ AccountSession × 3
   ├─ Strategies (hunt, restock, venda)
   └─ RateLimiter + Telemetry
```

Detalhes em [docs/arquitetura.md](docs/arquitetura.md).

## Estrutura

```
pokeidle-farm/
├─ worker/            # Python: sessão, protocolo, estratégias, telemetria
├─ web/               # Next.js (Vercel)
├─ supabase/          # migrations SQL + policies RLS
├─ docs/
│  ├─ arquitetura.md
│  ├─ protocolo.md    # mapa das mensagens WebSocket do jogo
│  ├─ regras-do-jogo.md
│  ├─ roadmap.md
│  └─ decisions/      # ADRs (registro de decisões)
└─ docker-compose.yml
```

## Decisões

| # | Decisão | Status |
|---|---|---|
| [0001](docs/decisions/0001-registrar-decisoes.md) | Registrar decisões em ADRs | Aceita |
| [0002](docs/decisions/0002-worker-headless-websocket.md) | Worker headless via WebSocket (sem navegador) | Aceita |
| [0003](docs/decisions/0003-supabase-como-intermediario.md) | Supabase como intermediário entre painel e worker | Aceita |
| [0004](docs/decisions/0004-hospedagem-digitalocean.md) | Hospedagem do worker na DigitalOcean | Aceita |
| [0005](docs/decisions/0005-auth-por-token-de-sessao.md) | Auth no jogo por token de sessão reaproveitado | Proposta |
| [0006](docs/decisions/0006-contas.md) | 4 contas: 3 de farm + 1 pessoal | Aceita |

## Segurança

- **Nunca** faça commit de tokens de sessão, `.env` ou chaves do Supabase. O repositório é público.
- Os segredos ficam no `.env` local ou do droplet. Use [.env.example](.env.example) como modelo.
