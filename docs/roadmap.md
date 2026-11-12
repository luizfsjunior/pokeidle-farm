# Roadmap

| Fase | Entrega | Onde roda | Status |
|---|---|---|---|
| 0 | Arquitetura e decisões documentadas | — | ✅ |
| 1 | Engenharia reversa: [protocolo.md](protocolo.md) preenchido | navegador | 🟡 mapeado a partir de referência, falta confirmar no DevTools |
| 2 | Núcleo do worker: sessão, barramento de eventos, interface de plugin, gravação de eventos brutos no Supabase. 1 conta, só escutando | local + Supabase | 🟡 código e testes prontos; falta rodar contra o jogo e um Supabase real |
| 2b | Simulador de eventos (`pokeidle-farm simulate`), para desenvolver métricas e painel sem o jogo | local + Supabase | ✅ |
| 4a | Métricas em camadas: agregados por hora e dia, definições, objetivos com ritmo, previsão e chance ([ADR 0012](decisions/0012-metricas-em-camadas.md)) | Supabase | ✅ testado em Postgres local com dados simulados |
| 3 | Escopo A: plugin da automação nativa (`auto.set`) + RateLimiter | local | ⬜ |
| 4 | Painel Next.js na Vercel, lendo as métricas da fase 4a (o Supabase já entra na fase 2, ver [ADR 0010](decisions/0010-supabase-desde-o-inicio.md)) | local + Vercel | ⬜ |
| 5 | Docker e deploy, subindo para 3 contas, numa máquina em casa ([ADR 0011](decisions/0011-worker-em-ip-residencial.md)) | casa | ⬜ |
| 6 | Escopo B: plugins de hunt, restock e captura | casa | ⬜ |
| 7 | Métricas derivadas do Mercado (valor dos drops em gold) e objetivos sobre elas | casa | ⬜ |
| 8 | Avaliar se compensa: 1–2 semanas de métricas e preços do Mercado | casa | ⬜ |
| 9 | Escopo C: plugins de venda e sniper no Mercado | casa | ⬜ |

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
