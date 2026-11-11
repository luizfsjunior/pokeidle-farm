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
