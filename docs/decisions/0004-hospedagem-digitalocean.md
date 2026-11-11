# 0004 — Hospedagem do worker na DigitalOcean

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O worker precisa rodar 24/7 com IP próprio. Os termos do jogo limitam 4 contas conectadas por rede, então um IP compartilhado com estranhos é um risco. Preços levantados em novembro de 2026:

| Opção | Preço/mês | Local | Observação |
|---|---|---|---|
| DigitalOcean Basic 512 MB | US$ 4 | EUA | cobrança por segundo, US$ 200 de crédito por 60 dias |
| DigitalOcean Basic 1 GB | US$ 6 | EUA | |
| Vultr 1 vCPU / 1 GB | US$ 7,50 | São Paulo | cobrança por hora |
| Hetzner CPX12 | €11,49 | EU/EUA | CX23 e CAX indisponíveis desde set/2026 |
| Render Background Worker | ~US$ 7 | — | IP de saída compartilhado; IP fixo custa US$ 100/mês |
| Oracle Free Tier | US$ 0 | — | sem shape disponível |

## Decisão

DigitalOcean como opção principal, começando pelos créditos grátis e pelo Basic de 512 MB. Sobe para 1 GB se a memória apertar.

## Consequências

- Custo estimado de ~R$ 21/mês (512 MB) ou ~R$ 32/mês (1 GB) depois dos créditos, já com IOF.
- Latência de ~120–150 ms até o servidor do jogo em São Paulo, aceitável para um jogo idle.
- Pendente: confirmar se a conta tem os créditos disponíveis.
- Como tudo roda em Docker, migrar para a Vultr São Paulo ou para a máquina local é só subir o mesmo `docker compose`.

## Questão em aberto: IP de datacenter

O DiuleJR/pokeidle-manager-online conecta **cada conta por um proxy ISP dedicado** e, por padrão, não deixa nada sair pelo IP da VPS. Isso sugere que o autor considera o IP de datacenter um risco. Os Termos (seção 8) dizem que a moderação pode consultar o tipo de conexão (residencial, móvel, datacenter, VPN), mas só cita isso para avaliar pedidos de liberação de rede. Não há proibição explícita de datacenter.

Antes de subir para o droplet, decidir entre:
1. Conectar direto do droplet (mais simples, risco desconhecido).
2. Usar um proxy residencial ou ISP (custo extra).
3. Rodar na máquina local, com IP residencial.

Vale perguntar no Discord oficial se conexão de datacenter é aceita.

## Alternativas consideradas

Ver a tabela acima. O Render foi descartado pelo IP compartilhado, e a Hetzner pelo preço e pela falta de planos baratos.
