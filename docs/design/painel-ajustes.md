# Painel: ajustes depois do tema fliperama (16/11/2026)

Retorno do usuário: o tema estava "arcade demais"; a barra de cima devia ter só o nome do app; a barra
ainda pulava ao rolar; as abas demoravam a trocar; e a interatividade que ele queria era mexer no worker
(clicar numa hunt e trocar, escolher o que capturar).

## Tema

- Continua escuro, com tons de azul-violeta mais calmos.
- Cartões com borda fina e cantos arredondados, sem molduras de pixel, linhas de TV, cursor piscando
  nem botões em relevo.
- O amarelo de ficha continua como cor de ação.
- A fonte pixel fica só nos títulos e nos números grandes.
- Os retratos dos pokémons e o palco em pixel art continuam.

## Casca de app (o fim dos pulos)

- A página tem a altura da tela (`100dvh`) e **só a área de conteúdo rola** (`.app-scroll`). A barra de
  cima e a barra de baixo do celular são linhas de um grid, sem `position: fixed` e sem `sticky`. Como o
  documento não rola, a barra de endereço do navegador não aparece nem some, e nada pula.
- **A casca está num layout** (`app/(painel)/layout.tsx`). Ao navegar, barra lateral e barras continuam
  na tela e só o conteúdo troca. O `loading.tsx` mostra um esqueleto na hora do clique.
  - As páginas foram movidas para o grupo `(painel)`; o login fica fora.
  - `<Shell>` nas páginas virou um fragmento.
- **A barra de cima** mostra só o logo e o nome do app. O placar saiu, e com ele duas consultas por página.

## Abas

`SectionTabs` grava a aba na URL com `history.replaceState`, em vez de `router.replace`. Antes, cada
troca pedia a página ao servidor de novo; agora é instantânea.

## Gaveta da hunt

Nas Hunts, o nome de cada hunt é um botão que abre uma gaveta (do lado no desktop, de baixo no celular).
Ela mostra o retrato, o nível, a área, gemas por 1.000 abates, os números medidos no período, as pedras e
quem está lá agora. Tem também **Trocar para esta hunt**, com a conta e o prazo, que usa o comando
`hunt.select` com a trava. Esc ou um toque fora fecha.
