# Painel (web/)

Next.js 16 (App Router) + Supabase Auth. Lê as contas, as métricas da fase 4a
([ADR 0012](../docs/decisions/0012-metricas-em-camadas.md)) e os objetivos.

- **Visão geral** (`/`): um cartão de treinador por conta (pokémon ativo, nível e XP, ouro, gemas, diamantes,
  equipe e coleção, de `account_profile`), status, último evento e os números de hoje por hora ativa.
  As imagens são os arquivos públicos do jogo (atlas por `looktype`; ver docs/design/painel-perfil.md).
- **Métricas** (`/metricas`): qualquer métrica por hora ou por dia, filtrando por conta e hunt (`metric_series`).
- **Comandos**: botões **Ping**, **Reconectar** e **Ligar/Desligar** em cada card; histórico em `/comandos`
  (com cancelar para os pendentes); foco (captura, ouro-xp-drop ou rank, comando `focus.set`), card "Rank
  semanal" (espécies, posição, alvo, fila e falhas, lidos de `events` por `lib/rank.ts`) e plugins de cada conta
  em `/contas/<id>`. Na visão geral, contas com o `rank` ligado mostram as espécies da semana e o alvo.
- **Página da conta**: cartão de treinador, Equipe, Coleção e Mochila (com os ícones dos itens), card Foco (captura, ouro-xp-drop, rank ou gemas), cards Rank e Gemas (alvo e potencial em
  gemas das melhores hunts) e os plugins em JSON recolhidos em "Avançado".
- **Hunts** (`/hunts`): as hunts visitadas no período (24 h, 7 ou 30 dias; por conta ou todas), com tempo, abates/h,
  gemas/h dos drops reais, ouro, drops, capturas e espécies novas (função `hunt_summary` no banco), e o catálogo das
  hunts que a conta alcança com as pedras que dropam, "gemas por 1.000 abates" e, onde há ritmo medido, gemas/h.
  O modelo das pedras está em `lib/hunts.ts` (o mesmo do worker).
- **Mercado** (`/mercado`): itens dropados nos últimos 7 dias, por conta ou todas, com a média de 7 dias do
  Mercado em gemas e ouro (último snapshot; sem vendas em ouro, o preço do NPC) e o valor total. A visão geral
  mostra o valor dos drops por hora ativa (métricas `drops_value_orb` e `drops_value_gold`, que usam o preço da
  hora de cada drop).
- **Vendas** (`/vendas`): anúncios das contas no Mercado (abertos, vendidos, cancelados), gemas recebidas e o que o
  seller fez, montados a partir dos eventos (docs/design/pagina-vendas.md).
- **Compensa?** (`/compensa`): renda mensal projetada em US$ (gemas dos drops × 0,85 × 0,009, como está e com
  24 h/dia), custo do mês (energia e fixo de VPS e proxy, editáveis em `evaluation_settings`), lucro, veredito e
  liquidez por item.
  Os números vêm das funções `evaluation_summary` e `evaluation_liquidity` no banco.
- **Objetivos** (`/objetivos`): criar sem SQL, progresso, ritmo, previsão e chance até o prazo; histórico das fotos em `/objetivos/<id>`.

## Segurança

- Usa **só a chave pública** (`sb_publishable_...`). O acesso aos dados é pelas policies RLS:
  cada usuário vê só as próprias contas. O app recusa subir se receber uma `sb_secret_`.
- A chave secreta (service_role) é só do worker. Nunca na Vercel, no `.env.local` do painel ou em commit.
- Login por e-mail e senha do usuário criado em **Authentication → Users**. A sessão é validada no
  servidor com `getClaims()` em `proxy.ts` (quem não entrou vai para `/login`) e nas Server Actions.
  Os dados são lidos no navegador com a mesma sessão, então o RLS vale igual.

## Como as peças se conectam

- **Páginas estáticas, dados no navegador** ([docs/design/painel-swr.md](../docs/design/painel-swr.md)). O
  layout de `(painel)` não lê cookie, então as páginas são pré-renderizadas e trocar de página é instantâneo.
  Cada página tem um carregador (`data.ts` ao lado, ou dentro do `View.tsx`) que recebe o cliente do Supabase;
  `usePanel` (em `lib/query/hooks.ts`) roda o carregador com o TanStack Query.
- **Cache persistido**: `lib/query/provider.tsx` guarda os resultados no `localStorage` (24 h). A página já
  vista aparece na hora e se atualiza por baixo, inclusive depois de fechar o app. O cache é apagado ao entrar
  e ao sair.
- **Carregamento**: `components/Loading.tsx` (`Ld`, `LdRows`, `LdBlock`). Título, descrição, abas e cabeçalhos
  aparecem direto; só os valores mostram a animação.
- **Ações** (comandos, objetivos, configurações) gravam no Supabase e depois invalidam as consultas
  (`useRefreshAll`) para a tela buscar de novo.
- **Imagens do jogo**: o atlas dos retratos é lido pelo servidor em `/api/atlas` (o site do jogo não libera CORS).

## Rodar no Codespaces (ou local)

```bash
cd web
npm ci                     # o devcontainer já faz isso num codespace novo
cp .env.example .env.local # e preencha a URL e a publishable key
npm run dev
```

Para conferir como em produção: `npm run build && npx next start -p 3100` e entrar pelo `/login` do localhost (o
login da Vercel não vale aqui). O `next dev` cria um `web/AGENTS.md`; não precisa commitar.

No Codespaces a porta 3000 abre sozinha no navegador (aba **Portas**). Para ter dados, rode antes
`pokeidle-farm simulate --nick <nick> --days 3` (ver [worker/README.md](../worker/README.md)).

## Vercel

1. **Add New → Project**, importe o repo e em **Root Directory** escolha `web`.
2. **Environment Variables**: `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.
3. Deploy. A região das funções fica em São Paulo (`gru1`, em `vercel.json`), perto do banco.
