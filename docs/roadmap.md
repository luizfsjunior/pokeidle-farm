# Roadmap

| Fase | Entrega | Onde roda | Status |
|---|---|---|---|
| 0 | Arquitetura e decisões documentadas | — | ✅ |
| 1 | Engenharia reversa: [protocolo.md](protocolo.md) preenchido | navegador | 🟡 mapeado a partir de referência, falta confirmar no DevTools |
| 2 | Núcleo do worker: sessão, barramento de eventos, interface de plugin, gravação de eventos brutos no Supabase. 1 conta, só escutando | local + Supabase | ⬜ |
| 3 | Escopo A: plugin da automação nativa (`auto.set`) + RateLimiter | local | ⬜ |
| 4 | Métricas em camadas e painel Next.js na Vercel (o Supabase já entra na fase 2, ver [ADR 0010](decisions/0010-supabase-desde-o-inicio.md)) | local + Vercel | ⬜ |
| 5 | Docker e deploy, subindo para 3 contas. **Antes:** decidir a conexão do droplet ([ADR 0004](decisions/0004-hospedagem-digitalocean.md)) | DigitalOcean | ⬜ |
| 6 | Escopo B: plugins de hunt, restock e captura | DigitalOcean | ⬜ |
| 7 | Métricas derivadas e objetivos (`goals`) com previsão | DigitalOcean | ⬜ |
| 8 | Avaliar se compensa: 1–2 semanas de métricas e preços do Mercado | DigitalOcean | ⬜ |
| 9 | Escopo C: plugins de venda e sniper no Mercado | DigitalOcean | ⬜ |

As fases seguem o [ADR 0008](decisions/0008-escopo-completo-modular.md): escopo completo, entregue em etapas (A → B → C).

## Critério de "compensa?"

```
renda_mensal_usd = Σ(valor_em_gemas_dos_drops_vendidos × (1 − comissão)) × 0,009
lucro = renda_mensal_usd − custo_do_droplet
```

Os créditos da DigitalOcean só começam a ser usados na fase 5. Até lá tudo roda localmente.

## Ideias futuras

### Agente orquestrador (depois que tudo estiver estável)

Um agente de IA que controla as contas usando os plugins e as ações como *tools*: escolher estratégias, ajustar configs, reagir a eventos e perseguir os objetivos (`goals`).

O que já deixamos preparado, para não ter retrabalho:
- Toda ação passa pelo `ActionGateway`, com schema Pydantic de entrada e de resultado. Isso vira, direto, a definição das tools.
- O agente usaria o mesmo gateway, com o mesmo rate limiter e as mesmas travas. Ele nunca fala direto com o WebSocket.
- O `ActionGateway` já tem modos (`observe_only` na fase 2). Dá para acrescentar um modo "o agente propõe, a pessoa aprova" antes de liberar autonomia.
- Os objetivos e métricas em camadas ([ADR 0008](decisions/0008-escopo-completo-modular.md)) dão ao agente algo mensurável para otimizar.

Pré-requisito: as fases até a 9 estáveis.
