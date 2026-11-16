# Painel: estética de fliperama (16/11/2026)

Pedido de 16/11: o redesign anterior "ainda tinha cara de padrão", a barra ainda "dava pulinhos" ao rolar,
e o usuário quis uma estética mais arcade e o título da página numa barra em cima.

## Direção

- **Noite de fliperama:**
  - fundo roxo-noite (`#120f24`) com uma grade de pixels sutil e um brilho no topo;
  - tema escuro sempre.
- **Moldura de pixel:** painéis, indicadores e botões têm bordas de 3 px com os cantos recortados
  (`box-shadow` em quatro lados, sem `border-radius`). Os cabeçalhos dos painéis ficam em faixa, com um
  quadradinho amarelo.
- **Cores:**
  - amarelo de ficha (`#ffcc33`) é a cor de ação: botões, abas e o item ativo;
  - ciano para links;
  - as moedas mantêm as cores (ouro, gemas roxas, diamantes ciano).
- **Cursor de menu "►"** marca o que está escolhido: página na barra lateral (piscando, menos com
  `prefers-reduced-motion`), aba de conta e período, e o título no HUD.
- **Tipografia:**
  - Pixelify Sans (`@fontsource-variable/pixelify-sans`) nos títulos, números grandes, botões e na barra
    de baixo;
  - Onest no texto corrido, para ler bem;
  - Silkscreen só na marca e no nick.
- **Botões:** em relevo, com luz em cima à esquerda e sombra embaixo à direita, e afundam ao clicar.
- **Campos e barras:** os campos são "fundos", com sombra interna. As barras de XP, passe e Pokédex são
  segmentadas.

## HUD

Barra no topo com "► Página" e o placar das contas: ouro, gemas e diamantes somados, e quantas contas
estão conectadas (`components/Hud.tsx`, lido do `account_profile`). No desktop ela fica fixa no topo.
No celular ela rola com a página.

## Imagens

- **Retrato do pokémon:**
  - vem do atlas do jogo por `looktype`;
  - se o atlas não carregar, usa o sprite da Pokédex nacional (PokeAPI, `species_id` ≤ 1025, com a
    versão shiny), ampliado 1,35× porque esse sprite tem margem transparente;
  - sem nenhum dos dois, aparece uma pokébola em pixel.
- **Palco do treinador:** um tufo de grama em pixel art (SVG feito à mão) sobre um céu escuro, com
  linhas de varredura de CRT.

## Os "pulinhos" ao rolar

Causas prováveis, todas tratadas:

- **`min-height: 100dvh`.** A altura dinâmica muda quando a barra do navegador aparece e some, e a página
  se reajustava enquanto rolava. Passou a ser `100vh`.
- **`content-visibility: auto` na Pokédex.** As células eram desenhadas ao entrar na tela, e a altura
  estimada mudava a rolagem. Foi removido.
- **`backdrop-filter` na barra de baixo.** O desfoque repinta a cada quadro ao rolar. Ela ficou sólida.
- **A barra de rolagem.** No desktop, aparecer e sumir deslocava o conteúdo para o lado (ao trocar de aba,
  por exemplo). Agora `scrollbar-gutter: stable` reserva o espaço.
- **No celular, nada fica sticky no topo.** Só a barra de baixo é fixa.
