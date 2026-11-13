# Painel (web/)

Next.js 16 (App Router) + Supabase Auth. Lê as contas, as métricas da fase 4a
([ADR 0012](../docs/decisions/0012-metricas-em-camadas.md)) e os objetivos.

- **Visão geral** (`/`): status de cada conta, último evento e os números de hoje por hora ativa.
- **Métricas** (`/metricas`): qualquer métrica por hora ou por dia, filtrando por conta e hunt (`metric_series`).
- **Comandos**: botões **Ping**, **Reconectar** e **Ligar/Desligar** em cada card; histórico em `/comandos`
  (com cancelar para os pendentes); plugins de cada conta em `/contas/<id>`.
- **Objetivos** (`/objetivos`): criar sem SQL, progresso, ritmo, previsão e chance até o prazo; histórico das fotos em `/objetivos/<id>`.

## Segurança

- Usa **só a chave pública** (`sb_publishable_...`). O acesso aos dados é pelas policies RLS:
  cada usuário vê só as próprias contas. O app recusa subir se receber uma `sb_secret_`.
- A chave secreta (service_role) é só do worker. Nunca na Vercel, no `.env.local` do painel ou em commit.
- Login por e-mail e senha do usuário criado em **Authentication → Users**. A sessão é validada no
  servidor com `getClaims()` em `proxy.ts` e em cada página.

## Rodar no Codespaces (ou local)

```bash
cd web
npm ci                     # o devcontainer já faz isso num codespace novo
cp .env.example .env.local # e preencha a URL e a publishable key
npm run dev
```

No Codespaces a porta 3000 abre sozinha no navegador (aba **Portas**). Para ter dados, rode antes
`pokeidle-farm simulate --nick <nick> --days 3` (ver [worker/README.md](../worker/README.md)).

## Vercel

1. **Add New → Project**, importe o repo e em **Root Directory** escolha `web`.
2. **Environment Variables**: `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.
3. Deploy. A região das funções fica em São Paulo (`gru1`, em `vercel.json`), perto do banco.
