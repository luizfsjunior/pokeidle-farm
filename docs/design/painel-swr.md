# Painel: navegação stale-while-revalidate e barra de cima que rola (16/11/2026)

Pedido de 16/11:
- a barra de cima pode rolar, e só a barra de baixo fica parada;
- o carregamento mostra o que é fixo e faz esqueleto só dos dados;
- uma página já vista abre na hora, com o que estava em cache, e troca quando os dados novos chegam;
- o esqueleto só aparece na primeira vez.

O nome disso é **stale-while-revalidate (SWR)**.

## Como ficou

- **Cache do navegador para páginas dinâmicas.** `experimental.staleTimes: { dynamic: 600 }`. A página
  já visitada fica 10 min no cache do App Router, e voltar a ela não vai ao servidor nem mostra
  esqueleto.
- **Revalidação por baixo.** O componente `<Revalidate at={Date.now()}>` fica no `PageHeader`, que toda
  página usa. Quando a página veio do cache (renderizada há mais de 5 s), ele chama `router.refresh()`:
  a tela antiga fica e a nova entra no lugar quando chega, sem esqueleto. Ele também atualiza ao voltar
  para a aba ou o app depois de 1 min.
- **Esqueleto só dos dados.** O `loading.tsx` de `(painel)` só aparece na primeira visita de cada página.
  Mantém a casca e mostra o título real da página (pelo caminho); só os blocos de dados viram esqueleto.
- **Barra de cima.** Fica dentro da área que rola e sobe com o conteúdo. A barra de baixo do celular
  continua parada, como linha do grid da casca, sem `position: fixed`.

## Pré-busca no toque e no mouse

Os links da barra lateral e das barras do celular chamam `router.prefetch` quando o mouse passa ou o
dedo encosta (`usePrefetch`). A página inteira entra no cache antes do clique, e até a primeira visita a
uma página do menu abre mais rápido.

## Limite

O cache vive na memória da aba ou do app aberto. Ao abrir o app do zero, a primeira página carrega com
esqueleto; daí em diante, as que já foram vistas abrem na hora. Guardar a página entre aberturas do app
(em localStorage, como faz o TanStack Query com persistência) exigiria buscar os dados no navegador, e não
no servidor. Isso é uma mudança maior, que fica para depois se fizer falta.
