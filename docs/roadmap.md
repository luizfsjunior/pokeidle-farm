# Roadmap

| Fase | Entrega | Onde roda | Status |
|---|---|---|---|
| 0 | Arquitetura e decisões documentadas | — | ✅ |
| 1 | Engenharia reversa: [protocolo.md](protocolo.md) preenchido | navegador | 🟡 mapeado a partir de referência, falta confirmar no DevTools |
| 2 | Worker só escutando: 1 conta, conecta com token e registra eventos, sem enviar ações | local | ⬜ |
| 3 | Ações com RateLimiter: trocar hunt e repor itens, 1 conta | local | ⬜ |
| 4 | Supabase (schema + RLS) e painel Next.js na Vercel | local + Vercel | ⬜ |
| 5 | Docker e deploy no droplet, subindo para 3 contas | DigitalOcean | ⬜ |
| 6 | Avaliar se compensa: 1–2 semanas de métricas e preços do Mercado | DigitalOcean | ⬜ |
| 7 | (Opcional) Venda automática no Mercado | DigitalOcean | ⬜ |

## Critério de "compensa?"

```
renda_mensal_usd = Σ(valor_em_gemas_dos_drops_vendidos × (1 − comissão)) × 0,009
lucro = renda_mensal_usd − custo_do_droplet
```

Os créditos da DigitalOcean só começam a ser usados na fase 5. Até lá tudo roda localmente.
