# Painel: redesign como app (16/11/2026)

Pedido de 16/11: o painel "parecia app de Streamlit". Os sinais eram título e parágrafo soltos, links
"Todas · conta" no meio do texto, explicações longas no topo e tudo empilhado numa coluna. A barra do
celular também "pulava" ao rolar.

## Casca

- **Desktop:** barra lateral escura e fixa, com a marca, as páginas em grupos (Jogo, Economia, Sistema),
  "Instalar o app" e o usuário com Sair. Entre 761 e 1.180 px ela vira um trilho só de ícones.
- **Celular:**
  - a barra do topo **rola com a página**: um topo fixo ou sticky pula quando a barra do navegador
    aparece e some, e foi isso que causava o pulo;
  - a barra de baixo é fixa, numa camada própria (`translateZ(0)`), com altura estável e a área segura do
    iPhone;
  - "Mais" abre uma gaveta (Esc e toque fora fecham).
- **Instalar o app** (`InstallApp`):
  - no Chrome, Edge e Android, o botão usa o pedido de instalação do navegador;
  - no iPhone mostra o caminho (Compartilhar → Adicionar à Tela de Início);
  - some quando o painel já está aberto como app.

## Peças (`components/Page.tsx`)

- `PageHeader`: título, uma linha de contexto, ações à direita e uma linha de filtros.
- `AccountTabs` e `LinkTabs`: abas segmentadas por link no lugar dos links "Todas · conta" no texto.
- `Panel`: cartão com cabeçalho (título e meta) e corpo. `flush` deixa a tabela de ponta a ponta, com a
  nota embaixo.
- `Kpi`: faixa de indicadores no topo das páginas (Contas, Mercado, Vendas).
- `Explain`: "Como é calculado", recolhido. As explicações longas saem do topo das páginas.
- `SectionTabs`: abas na página da conta (Resumo, Equipe e coleção, Estratégia, Ajustes), com a aba na URL.

## Tema

- O fundo é cinza-azulado frio, com cartões brancos, borda fina e sombra mínima. A barra lateral é escura
  nos dois temas.
- A cor de ação é o verde da grama (`--accent` #0f7a60; #3cc49f no escuro). As moedas mantêm as cores.
- Tipografia: Onest no corpo; Silkscreen só na marca e no nick do treinador.
- Tabelas: cabeçalho em faixa, linha destacada sob o ponteiro e números alinhados à direita.
- Formulários: campos com altura única e foco visível.
