# 0011 — Worker em IP residencial

- **Status:** Aceita
- **Data:** 2026-11-12
- **Substitui:** [0004](0004-hospedagem-digitalocean.md)

## Contexto

Em 2026-11-12, o primeiro teste real do worker (1 conta de farm, modo `observe_only`) rodou num droplet da DigitalOcean em NYC2. O servidor recusou a conexão com `{"t":"erro","chave":"auth.provedorBanido"}`.

Os Termos (seção 8) já diziam que a moderação pode consultar o tipo de conexão (residencial, móvel, datacenter, VPN) via ipapi.is. O resultado mostra que pelo menos a DigitalOcean está bloqueada de forma ativa, e é provável que outros provedores de nuvem também estejam.

## Decisão

- O worker roda numa **máquina com IP residencial** (o PC de casa, um notebook ou um mini PC / Raspberry Pi ligado 24/7).
- **Não** usamos proxy, VPN nem outro truque para contornar o bloqueio por provedor. O bloqueio é uma proteção deliberada do jogo, e contorná-lo seria "burlar limites do jogo" (Termos, seção 5).
- O droplet da DigitalOcean é destruído.
- O Supabase e o painel na Vercel continuam como estão: eles não conectam no jogo.

## Consequências

- Custo de hospedagem perto de zero (só energia).
- A disponibilidade 24/7 depende da máquina de casa e da internet. A reconexão com backoff, o lease e o buffer local da telemetria já cobrem quedas curtas.
- O limite por rede continua valendo: até 4 contas conectadas na rede de casa, contando a conta pessoal se ela estiver jogando ao mesmo tempo. Com 3 de farm + 1 pessoal, fica exatamente no limite.
- O `docker-compose.yml` passou a usar `restart: on-failure`. Uma conta rejeitada encerra o worker com código 0, e o container não volta a reconectar sozinho contra um bloqueio.

## Alternativas consideradas

- **Outro provedor de nuvem (Vultr, Hetzner etc.):** provavelmente bloqueado pelo mesmo critério. Testar seria arriscar a conta sem necessidade.
- **Proxy residencial ou ISP** (como faz o DiuleJR/pokeidle-manager-online): rejeitada, por contornar uma proteção do jogo.
