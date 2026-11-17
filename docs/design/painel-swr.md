# Painel: dados no navegador com cache (stale-while-revalidate)

Pedido de 16/11: a página já vista abre na hora e troca quando chegam os dados novos; título, descrição,
abas e cabeçalhos aparecem direto e só os dados mostram carregamento; o painel no celular tem que ser rápido.

## Versão 1 (descartada): servidor + `router.refresh()`

As páginas buscavam tudo no servidor, o `staleTimes` guardava a página no cache do App Router e um
`<Revalidate>` chamava `router.refresh()` quando ela vinha do cache. Medido no celular em 16/11:

- **o `router.refresh()` apaga o cache de todas as páginas**, não só a atual: ver A, ir para B (que se
  atualiza) e voltar para A mostrava o esqueleto de novo. Só a última página ficava em cache;
- o `loading.tsx` era um esqueleto genérico (4 KPIs e um bloco) para todas as páginas, até o subtítulo;
- cada página esperava todas as consultas antes de mostrar qualquer coisa (Vendas: 3 a 6 s).

## Versão 2 (atual): TanStack Query com cache persistido

- **Páginas estáticas.** O layout de `(painel)` não lê cookie (quem não entrou é barrado pelo `proxy.ts`),
  então todas as páginas saem pré-renderizadas: trocar de página é instantâneo (~25 ms medidos).
- **Dados no navegador.** Cada página tem um carregador (`data.ts` ao lado da página, ou dentro do
  `View.tsx`) que recebe o cliente do Supabase e devolve o que a tela precisa. Roda no navegador
  (`lib/query/hooks.ts`, `usePanel`), com a sessão dos cookies e o mesmo RLS do servidor.
- **Cache persistido.** `lib/query/provider.tsx`: o resultado de cada consulta fica no `localStorage`
  (`pf-cache-v1`, 24 h), com `Map` e `Set` serializados. A página já vista mostra o cache na hora e busca a
  versão nova por baixo (`staleTime` de 5 s); vale também depois de fechar e abrir o app. Uma linha fina
  amarela no topo (`FetchBar`) aparece enquanto busca.
- **Carregamento só dos dados.** `components/Loading.tsx`: `Ld` (barrinha no lugar de um valor), `LdRows`
  (linhas de tabela debaixo do cabeçalho real) e `LdBlock` (gráfico ou card). Título, descrição, abas e
  cabeçalhos são renderizados direto.
- **Depois de agir**, `useCommand`, o formulário do Compensa e as ações dos objetivos chamam
  `invalidateQueries` (`useRefreshAll`) em vez de `router.refresh()`. O `AutoRefresh` invalida as consultas
  (ou só a da página) a cada intervalo.
- **Atlas dos retratos** pelo servidor, em `/api/atlas` (o site do jogo não libera CORS).

## Cuidados (gotchas)

- **Hidratação.** O HTML estático vem sem dados, mas o cache do `localStorage` pode já estar no primeiro
  render do navegador. `usePanel`, `useAtlas` e `useMe` escondem os dados até hidratar
  (`useSyncExternalStore`); sem isso o React acusa a diferença (#418) e refaz a árvore.
- **Usuário trocado.** O cache é apagado ao entrar (`login/page.tsx`) e ao sair (botões Sair), para não
  mostrar dados de outro usuário no mesmo aparelho. Mudou o formato dos dados guardados? Suba o `buster`
  no provider.
- **Consultas em `events` com RLS.** `like "seller.%"` não usa o índice `(type, received_at)` e, com o RLS,
  o banco varria todos os eventos da conta (~7 s). Use lista fechada de tipos (`in`).
- **`[hidden]`** tem `display: none !important` no CSS: as abas da conta usam `hidden` em `.stack`, que tem
  `display: grid` e ganhava.
- **Rodar local:** `web/.env.local` com `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
  (a chave pública), `npm run build && npx next start`, e entrar pelo `/login` do localhost.
