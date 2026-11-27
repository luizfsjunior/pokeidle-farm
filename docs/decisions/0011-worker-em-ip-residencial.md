# 0011 — Worker em IP residencial

- **Status:** Aceita, revista pela [0013](0013-proxy-autorizado.md) em 2026-11-16 (proxy/VPN liberado pelo suporte)
- **Data:** 2026-11-12

## Contexto

Em 2026-11-12, o primeiro teste real do worker (1 conta de farm, modo `observe_only`) rodou num IP de datacenter. O jogo recusou a conexão com `{"t":"erro","chave":"auth.provedorBanido"}`.

Os Termos (seção 8) já diziam que a moderação pode consultar o tipo de conexão (residencial, móvel, datacenter, VPN) via ipapi.is. O resultado mostra que IP de datacenter é bloqueado de forma ativa.

## Decisão

- O worker roda numa **máquina com IP residencial** (o PC de casa, um notebook ou um mini PC / Raspberry Pi ligado 24/7).
- **Não** usamos proxy, VPN nem outro truque para contornar o bloqueio por provedor. O bloqueio é uma proteção deliberada do jogo, e contorná-lo seria "burlar limites do jogo" (Termos, seção 5).
- O Supabase e o painel na Vercel continuam como estão: eles não conectam no jogo.

## Consequências

- Custo perto de zero (só energia).
- A disponibilidade 24/7 depende da máquina de casa e da internet. A reconexão com backoff, o lease e o buffer local da telemetria já cobrem quedas curtas.
- O limite por rede continua valendo: até 4 contas conectadas na rede de casa, contando a conta pessoal se ela estiver jogando ao mesmo tempo. Com 3 de farm + 1 pessoal, fica exatamente no limite.
- O `docker-compose.yml` passou a usar `restart: on-failure`. Uma conta rejeitada encerra o worker com código 0, e o container não volta a reconectar sozinho contra um bloqueio.

## Pendência: pedido formal ao suporte

Em 2026-11-12, enviamos um e-mail para support@pokeidle.io perguntando:
1. se a automação pode rodar a partir de um IP de datacenter, com liberação do IP fixo (a seção 8 dos Termos menciona pedidos de liberação de rede);
2. se não, se conectar por um proxy residencial dedicado é permitido ou se conta como burlar limites.

Até a resposta, o worker roda só em IP residencial, sem proxy. Uma resposta positiva vira um novo ADR que revisa este. Prazo de resposta pelos Termos: até 15 dias.

## Alternativas consideradas

- **Proxy residencial ou ISP** (como faz o DiuleJR/pokeidle-manager-online): rejeitada, por contornar uma proteção do jogo.
