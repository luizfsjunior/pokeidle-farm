# Painel (web/)

Next.js 16 (App Router) + Supabase Auth. Lê as contas, as métricas da fase 4a
([ADR 0012](../docs/decisions/0012-metricas-em-camadas.md)) e os objetivos.

Navegação (docs/design/painel-ux-v2.md): no celular, **Contas, Pokédex, Hunts, Economia** e **Mais** (Bosses,
Objetivos, Métricas, Comandos). As páginas com dados por conta usam o seletor `AccountPicker` (`?conta=`), que lembra
a última conta escolhida (`localStorage`, chave `pf-conta`).

- **Contas** (`/`): um cartão de treinador por conta (pokémon ativo, nível, moedas, equipe, de `account_profile`) e
  os números de hoje por hora ativa. Só o botão Abrir (e Reconectar quando a conta ligada não está pronta).
- **Conta** (`/contas/<id>`), 3 abas:
  - **Agora**: cartão do treinador; **Fazendo agora** (foco, hunt e captura, cada linha abre a ação: `focus.set`,
    `hunt.select` com busca e filtro pelo nível do treinador, `capture.stop`); plano de XP até o marco; treinar a
    equipe; Outland; rank; bônus, passe e evolução recolhidos.
  - **Pokémons**: equipe (tornar ativo, pôr e tirar), coleção, mochila e a ficha de cada pokémon.
  - **Ajustes**: os plugins em JSON (um por linha, recolhidos) e os últimos comandos.
- **Pokédex** (`/pokedex`): catálogo do jogo cruzado com a Pokédex da conta (as formas de mesmo nome num card),
  ficha da espécie, chance de captura por bola e o botão de capturar (`capture.start`).
- **Hunts** (`/hunts`): por conta, o que cada hunt rendeu no período (`hunt_summary`); tocar numa hunt abre a
  gaveta para trocar (respeita o nível do treinador) ou capturar.
- **Bosses** (`/bosses`): os trios lendários por região, prêmio do dia e quem da conta serve contra cada um.
- **Economia** (`/economia`, no lugar de Vendas, Mercado e Compensa, que redirecionam): o veredito "Compensa?"
  (`evaluation_summary`: drops das contas de farm × preço, menos o custo de `evaluation_settings`), o que o Mercado
  já pagou, os anúncios (montados dos eventos por `lib/sales.ts`), o que o seller fez e os drops de 7 dias.
  **Pedras não contam como renda** (vendem a 2 gemas): ficam fora de `drops_value_orb` e dos totais.
- **Objetivos** (`/objetivos`): progresso, ritmo e previsão; o formulário mostra o essencial e esconde os filtros
  finos em "Mais opções". Histórico das fotos em `/objetivos/<id>`.
- **Métricas** (`/metricas`): qualquer métrica por hora ou por dia (`metric_series`). **Comandos**: histórico.

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
- **Pouco texto na tela**: explicações longas ficam no "ⓘ"; detalhe que pouca gente abre fica em `Fold` (seção
  recolhida, `components/Page.tsx`). Números usam a fonte comum (`--font-num`): a pixelada fazia o 3 parecer 9.
  O "ⓘ" é o `Hint` (`PageHeader` e `Panel` aceitam `hint`). Comparações dentro de tabelas usam a barrinha `Bar`. No celular, toda tabela com `<thead>` vira
  cartões (`components/TableLabels.tsx` copia o cabeçalho para o `data-label` de cada célula; `data-keep` evita).
- **Ações** (comandos, objetivos, configurações) gravam no Supabase e depois invalidam as consultas
  (`useRefreshAll`) para a tela buscar de novo.
- **Uma regra para cada número** (docs/design/painel-ux-v2.md): preço de hoje em gemas, comissão e US$ por gema
  só em `lib/money.ts`; status de comando só em `components/CommandStatus.tsx`; catálogo de hunts sempre por
  `lib/catalog.ts` (a API devolve no máximo 1.000 linhas e o jogo tem mais hunts que isso); bolas pelas regras do
  jogo (`loadGameRules`). Antes cada tela tinha a sua versão e os números não batiam.
- **Erro não vira "nada"**: carregador que depende de uma consulta essencial lança o erro (em vez de devolver lista
  vazia); a tela mantém os últimos dados bons do cache e mostra o aviso.
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
