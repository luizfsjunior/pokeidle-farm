# pokeidle-farm

Automação de farm para o [pokeidle.io](https://pokeidle.io), com um worker headless em Python e um painel web para acompanhar e controlar as contas.

> Projeto pessoal, sem vínculo com o pokeidle.io. Os Termos do jogo (seção 5, "Automação") permitem automações desde que sigam as mesmas regras de quem joga na mão: sem explorar falhas, sem burlar limites (contas por pessoa/rede, travas e retenções do Mercado) e sem sobrecarregar o servidor. Veja [docs/regras-do-jogo.md](docs/regras-do-jogo.md).

## Status

🟡 Em desenvolvimento: worker rodando contra o jogo em IP residencial, com o primeiro plugin que age no jogo (`restock`: escolhe a bola e repõe consumíveis), métricas (incluindo ouro líquido) e painel v1 no ar. Detalhes no [roadmap](docs/roadmap.md).

## Visão geral

```
[Painel Next.js — Vercel] ──Supabase Auth (senha)───┐
                                                     ▼
                                        [Supabase: Postgres + Realtime]
                                                     ▲
                    lê comandos / grava estado e métricas
                                                     │
[Máquina com IP residencial — Docker] worker Python (asyncio) ── WebSocket ──> pokeidle.io
   ├─ AccountSession × 3
   ├─ Strategies (hunt, restock, venda)
   └─ RateLimiter + Telemetry
```

Detalhes em [docs/arquitetura.md](docs/arquitetura.md).

## Estrutura

```
pokeidle-farm/
├─ worker/            # Python: sessão, protocolo, estratégias, telemetria
├─ web/               # painel Next.js (Vercel), ver web/README.md
├─ supabase/          # migrations SQL + policies RLS; tests/ para validar num Postgres local
├─ docs/
│  ├─ arquitetura.md
│  ├─ protocolo.md    # mapa das mensagens WebSocket do jogo
│  ├─ regras-do-jogo.md
│  ├─ roadmap.md
│  ├─ diario.md      # o que foi feito a cada dia, problemas e pendências
│  ├─ design/       # documentos de design por fase
│  ├─ deploy.md     # como subir Supabase + worker
│  └─ decisions/      # ADRs (registro de decisões)
└─ docker-compose.yml
```

## Decisões

| # | Decisão | Status |
|---|---|---|
| [0001](docs/decisions/0001-registrar-decisoes.md) | Registrar decisões em ADRs | Aceita |
| [0002](docs/decisions/0002-worker-headless-websocket.md) | Worker headless via WebSocket (sem navegador) | Aceita |
| [0003](docs/decisions/0003-supabase-como-intermediario.md) | Supabase como intermediário entre painel e worker | Aceita |
| [0004](docs/decisions/0004-hospedagem-digitalocean.md) | Hospedagem do worker na DigitalOcean | Substituída pela 0011 |
| [0005](docs/decisions/0005-auth-por-token-de-sessao.md) | Auth no jogo por token de sessão reaproveitado | Proposta |
| [0006](docs/decisions/0006-contas.md) | 4 contas: 3 de farm + 1 pessoal | Aceita (alterada pela 0007) |
| [0007](docs/decisions/0007-contas-farm-email-senha.md) | Contas de farm com e-mail e senha; senhas fora do worker | Aceita |
| [0008](docs/decisions/0008-escopo-completo-modular.md) | Escopo completo (até o Mercado), com estratégias plugáveis e métricas em camadas | Aceita |
| [0009](docs/decisions/0009-licenca-agpl.md) | Licença AGPL-3.0 | Aceita |
| [0010](docs/decisions/0010-supabase-desde-o-inicio.md) | Supabase desde o início do desenvolvimento | Aceita |
| [0011](docs/decisions/0011-worker-em-ip-residencial.md) | Worker em IP residencial (o jogo bloqueia a DigitalOcean) | Aceita |
| [0012](docs/decisions/0012-metricas-em-camadas.md) | Métricas em camadas no Postgres, com objetivos e previsão | Aceita |

## Referências e créditos

Este projeto se apoia no trabalho da comunidade do pokeidle.io:

- **[DiuleJR/pokeidle-manager-online](https://github.com/DiuleJR/pokeidle-manager-online)** (AGPL-3.0), bot headless em Python com painel web. O mapeamento inicial do protocolo WebSocket em [docs/protocolo.md](docs/protocolo.md) se baseia na leitura do código dele: handshake, mensagens, códigos de erro e o comportamento do token. Obrigado pelo trabalho de engenharia reversa! As duas licenças são AGPL-3.0, então trechos reaproveitados de lá mantêm o aviso de origem no próprio arquivo.
- [Romeu-q/ThoseIdles](https://github.com/Romeu-q/ThoseIdles), gerenciador de sessões que documenta o `hello` e o `ping`.
- [ZaryImortal/pokeidle-piloto](https://github.com/ZaryImortal/pokeidle-piloto), extensão de automação, referência de funcionalidades.
- [Termos de Uso do pokeidle.io](https://pokeidle.io/terms).

Se você é autor de algum desses projetos e quer que algo seja ajustado, abra uma issue.

## Licença

[AGPL-3.0](LICENSE). Ver [ADR 0009](docs/decisions/0009-licenca-agpl.md).

## Segurança

- **Nunca** faça commit de tokens de sessão, `.env` ou chaves do Supabase. O repositório é público.
- Os segredos ficam no `.env` da máquina que roda o worker. Use [.env.example](.env.example) como modelo.
