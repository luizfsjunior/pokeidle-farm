# pokeidle-farm

Automação de farm para o [pokeidle.io](https://pokeidle.io), com um worker headless em Python e um painel web para acompanhar e controlar as contas.

> Projeto pessoal, sem vínculo com o pokeidle.io. Os Termos do jogo (seção 5, "Automação") permitem automações desde que sigam as mesmas regras de quem joga na mão: sem explorar falhas, sem burlar limites (contas por pessoa/rede, travas e retenções do Mercado) e sem sobrecarregar o servidor. Veja [docs/regras-do-jogo.md](docs/regras-do-jogo.md).

## Status

🟡 Em uso numa conta, crescendo por fases (detalhes no [roadmap](docs/roadmap.md)):

- **No ar:** worker num VPS com a saída do jogo por proxy ([ADR 0013](docs/decisions/0013-vps-com-proxy-autorizado.md)),
  4 contas; plugins `restock` (bola e consumíveis), `gems` (modo XP: a hunt de mais XP/h que o pokémon aguenta),
  `team_train` (treina a equipe), `watchdog` (vigia: cura, morte em loop, conta parada), `rank`, `capture_target`,
  `ball_thrower` (joga a bola à mão: shiny sempre e a espécie da captura; a bola automática do jogo exige VIP),
  `hunt_hold`, `market_prices` e `seller`; métricas com objetivos; painel com visão geral e alertas, a conta em 4
  abas (Agora, Pokémons, Itens com loja e Mercado, Ajustes) e `/economia`.
- **Modo padrão:** XP. Pedras não são renda (vendem a 2 gemas); o modo gemas ficou só para quem já estava nele.
- **Juntando dados:** o veredito do "Compensa?" (renda em gemas contra o custo de energia) fica confiável com 7 dias
  de preços, por volta de 22/11/2026.
- **Próximo:** fase 5, rodar as 3 contas de farm.

## Visão geral

```
[Painel Next.js — Vercel] ──Supabase Auth (senha)───┐
                                                     ▼
                                        [Supabase: Postgres + Realtime]
                                                     ▲
                    lê comandos / grava estado e métricas
                                                     │
[VPS — Docker] worker Python (asyncio) ── WebSocket (proxy autorizado) ──> pokeidle.io
   ├─ AccountSession × 4
   ├─ Plugins: restock, gems (modo XP), team_train, watchdog, rank, capture_target, ball_thrower, hunt_hold, seller...
   └─ ActionGateway (RateLimiter + travas por dono) + telemetry
```

Detalhes em [docs/arquitetura.md](docs/arquitetura.md).

## Como rodar e manter

- **Worker** (Python, Docker): [worker/README.md](worker/README.md): `.env`, `docker compose up -d --build`, testes
  (`pytest` e `ruff` num container) e como ligar cada plugin.
- **Painel** (Next.js): [web/README.md](web/README.md): variáveis, `npm run dev`, `npm run typecheck` e o deploy na
  Vercel (a cada push na `main`).
- **Banco** (Supabase): as migrations em `supabase/migrations` são aplicadas no push para a `main`;
  teste antes num Postgres local com [supabase/tests/README.md](supabase/tests/README.md).
- **Deploy do zero:** [docs/deploy.md](docs/deploy.md). **O que mudou e por quê:** [docs/diario.md](docs/diario.md)
  e os desenhos em `docs/design/`.

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
| [0013](docs/decisions/0013-vps-com-proxy-autorizado.md) | Worker em VPS com a saída do jogo por proxy ou VPN de IP fixo (liberado pelo suporte) | Aceita |

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
