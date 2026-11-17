# Roadmap

| Fase | Entrega | Onde roda | Status |
|---|---|---|---|
| 0 | Arquitetura e decisões documentadas | — | ✅ |
| 1 | Engenharia reversa: [protocolo.md](protocolo.md) preenchido | navegador | ✅ handshake, sessão, abates, captura, drops, troca de hunt, Lançar até Capturar, Top Catch, ranking e médias do Mercado confirmados (12 a 15/11); só o `sessao.renovada` ainda não chegou |
| 2 | Núcleo do worker: sessão, barramento de eventos, interface de plugin, gravação de eventos brutos no Supabase. 1 conta, só escutando | local + Supabase | ✅ rodando contra o jogo desde 12/11; tradutor v2 (formato real do `estado`, sem ruído no banco) |
| 2b | Simulador de eventos (`pokeidle-farm simulate`), para desenvolver métricas e painel sem o jogo | local + Supabase | ✅ |
| 4a | Métricas em camadas: agregados por hora e dia, definições, objetivos com ritmo, previsão e chance ([ADR 0012](decisions/0012-metricas-em-camadas.md)) | Supabase | ✅ testado em Postgres local com dados simulados |
| 3 | Escopo A: plugin da automação nativa (`auto.set`) + RateLimiter | local | ✅ 3a ([reposição e escolha da bola](design/fase-3-reposicao.md)) e 3b (rank semanal: [desenho](design/fase-3b-rank-semanal.md), [ensaio](design/fase-3b-plugin-rank.md), [agindo de verdade](design/fase-3b-rank-ligado.md) e [métricas e card](design/fase-3b-metricas-e-card.md)) ligados em `luizfsjunior_1` |
| 4 | Painel Next.js na Vercel, lendo as métricas da fase 4a (o Supabase já entra na fase 2, ver [ADR 0010](decisions/0010-supabase-desde-o-inicio.md)) | local + Vercel | ✅ no ar: visão geral, métricas, objetivos, [comandos](design/fase-4b-comandos.md), foco e rank por conta, Mercado e Compensa? |
| 5 | Docker e deploy, subindo para 3 contas, numa máquina em casa ([ADR 0011](decisions/0011-worker-em-ip-residencial.md)) | casa | 🟡 worker num droplet da DigitalOcean com proxy desde 16/11 ([ADR 0013](decisions/0013-vps-com-proxy-autorizado.md), ~US$ 10/mês); antes, no Docker do PC de casa; falta cadastrar e rodar as outras duas contas |
| 6 | Escopo B: plugins de hunt, restock e captura | casa | 🟡 [foco XP](design/foco-xp.md) e [foco gemas](design/foco-gemas-e-ritmo.md) prontos em 15/11 (ritmo projetado pelo nível do ativo); [foco gemas](design/foco-gemas-e-ritmo.md) pronto em 15/11 (hunt escolhida pelo valor das pedras em gemas, com teto de liquidez); ligar quando decidir trocar o foco da conta |
| 7 | Métricas derivadas do Mercado (valor dos drops em gold) e objetivos sobre elas | casa | ✅ [no ar desde 15/11](design/fase-7-precos-do-mercado.md): médias do Mercado por hora, catálogo de itens, valor dos drops em gemas e ouro e a página `/mercado` |
| 8 | Avaliar se compensa: 1–2 semanas de métricas e preços do Mercado | casa | 🟡 [página `/compensa`](design/fase-8-compensa.md) pronta em 15/11 (renda em gemas, custo de energia, liquidez); o veredito fica confiável com 7 dias de preços (a partir de 22/11) |
| 9 | Escopo C: plugins de venda e sniper no Mercado | casa | 🟡 [venda de pedras](design/fase-9-venda-de-pedras.md) em ensaio desde 15/11 (guarda 5, anuncia 1 abaixo do menor anúncio com piso de 85% da média); sniper: não começou |

As fases seguem o [ADR 0008](decisions/0008-escopo-completo-modular.md): escopo completo, entregue em etapas (A → B → C).

## Critério de "compensa?"

```
renda_mensal_usd = Σ(valor_em_gemas_dos_drops_vendidos × (1 − comissão)) × 0,009
lucro = renda_mensal_usd − custo_da_máquina (energia)
```

O worker roda numa máquina com IP residencial: o jogo bloqueia a DigitalOcean ([ADR 0011](decisions/0011-worker-em-ip-residencial.md)).

## Ideias futuras

### Agente orquestrador (depois que tudo estiver estável)

Um agente de IA que controla as contas usando os plugins e as ações como *tools*: escolher estratégias, ajustar configs, reagir a eventos e perseguir os objetivos (`goals`).

O que já deixamos preparado, para não ter retrabalho:
- Toda ação passa pelo `ActionGateway`, com schema Pydantic de entrada e de resultado. Isso vira, direto, a definição das tools.
- O agente usaria o mesmo gateway, com o mesmo rate limiter e as mesmas travas. Ele nunca fala direto com o WebSocket.
- O `ActionGateway` já tem modos (`observe_only` na fase 2). Dá para acrescentar um modo "o agente propõe, a pessoa aprova" antes de liberar autonomia.
- Os objetivos e métricas em camadas ([ADR 0008](decisions/0008-escopo-completo-modular.md)) dão ao agente algo mensurável para otimizar.

Pré-requisito: as fases até a 9 estáveis.
