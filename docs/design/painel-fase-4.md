# Painel, fase 4: celular, instalável e as outras páginas no estilo novo (16/11/2026)

- **Celular** (até 760 px):
  - o menu do topo vira uma barra embaixo com Contas, Pokédex, Vendas e Hunts;
  - "Mais" abre uma gaveta com Métricas, Objetivos, Mercado, Compensa?, Comandos, o e-mail e Sair;
  - o topo fica fixo e só com a marca;
  - a gaveta respeita `prefers-reduced-motion`, e o espaço da barra respeita a área segura do iPhone;
  - na Pokédex, o detalhe da espécie abre acima da barra.
- **Instalável (PWA)**:
  - `app/manifest.ts` (standalone, ícones 192/512 e maskable), `apple-icon.png`, `icon.png`, `appleWebApp`
    e `theme-color` claro e escuro;
  - o `proxy.ts` deixa o `manifest.webmanifest` sem login, porque o navegador busca o manifest sem cookies;
  - o ícone é uma moeda dourada com "P" em pixel sobre um tufo de grama, desenhado para o projeto.
- **Desktop**:
  - a página atual fica sublinhada no menu, sem barra de rolagem;
  - o e-mail some abaixo de 1.240 px para o menu caber;
  - a marca usa a fonte pixel.
- **Outras páginas**:
  - Hunts mostra o retrato da espécie de cada hunt (atlas do jogo);
  - Mercado mostra o ícone de cada item;
  - em todas as tabelas, a linha fica destacada sob o ponteiro e os cabeçalhos ficam compactos.
  - Inputs, selects e textareas mostram o foco de teclado.
