# Painel: revisão de UX e números (17/11/2026)

Revisão do `web/` depois de o painel crescer por fases: 10 páginas, 4 abas na conta, o mesmo dado calculado de
jeitos diferentes em telas diferentes e muita explicação na tela. Decisões tomadas com o usuário em 17/11.

## 1. Uma regra de gemas

O mesmo drop valia até 4 preços: a métrica `drops_value_orb` (menor entre a média de 7 dias e o menor anúncio,
gravado na hora do drop), o Mercado (mediana das vendas limitada pelo menor anúncio), o catálogo de hunts (a regra
antiga das pedras) e a Outland (mediana menos 15%). A Compensa chegou a dizer US$ 144/mês de lucro com 0 vendas.

- **Pedras não são fonte de gemas.** Vendem a 2 gemas com milhares na fila (análise de 17/11). Os itens de
  `game_items.category = 'stone'` (pedras de evolução, Shiny Stones e Rough Gemstone) saem da renda: a métrica
  `drops_value_orb` não as conta (migração `20261118000000_gemas_sem_pedras.sql`, recalculando 30 dias). Elas
  continuam no estoque, no seller e na página Economia, marcadas como "fora da renda".
- **Preço de hoje** = a referência (mediana das vendas reais com 3+ vendas, senão a média de 7 dias do jogo),
  limitada pelo menor anúncio aberto. Uma função só no painel: `gemPrice` em `web/lib/money.ts`.
- **Taxa e saque num lugar só** no painel (`web/lib/money.ts`): 15% de comissão em item vendido por gemas e
  US$ 0,009 por gema (fase-8-compensa.md; os 13%/10%/7,5% de `regras.economia` são só de pokémon). Antes a conta
  estava escrita de 3 jeitos (um deles já sem a comissão).
- A renda da Compensa conta **só as contas de farm** (a pessoal ficava somada).
- A tabela de liquidez saiu: era só sobre pedras e a função levava 19 s (estourava o tempo do banco).

## 2. Navegação

| Antes | Depois |
|---|---|
| Contas, Pokédex, Hunts, Bosses, Objetivos, Métricas, Vendas, Mercado, Compensa, Comandos | Contas, Pokédex, Hunts, **Economia**, Mais (Bosses, Objetivos, Métricas, Comandos) |
| Abas de conta (chips em 2 linhas) em 5 páginas | Um seletor de conta compacto, lembrado entre páginas |

`/vendas`, `/mercado` e `/compensa` redirecionam para `/economia` (atalhos e o app instalado continuam abrindo).

## 3. Página da conta: 3 abas

- **Agora**: cartão do treinador; "Fazendo agora" (foco, hunt, captura, com as ações recolhidas em cada linha);
  plano até o marco; treinar a equipe; Outland; rank; bônus, passe e evolução no fim.
- **Pokémons**: equipe (com as ações), coleção, mochila.
- **Ajustes**: plugins em JSON e os últimos comandos.

## 4. Correções

- Números em fonte legível (a pixelada fazia o 3 parecer 9: nível 380 lia "980"); a pixelada fica nos títulos.
- Escolher hunt: busca em vez de um `<select>` de 268 opções, e filtra pelo **nível do treinador** (o jogo tranca
  por ele; antes usava o nível do pokémon + 5). A gaveta da hunt também respeita o nível da conta escolhida.
- Pokédex: contadores contam por card (as formas juntas), filtros recolhidos.
- Bolas: nomes e preços das regras do jogo (`catalogoBolas`), não de tabelas no código.
- Outland: "Faltam NaN níveis" com evento sem `trainer_level`.
- Visão geral: cartões de conta mais curtos; o quadro "Gemas nas contas" (sempre 0) saiu.
- Objetivos: o formulário fica recolhido e mostra o essencial; os filtros finos em "Mais filtros"; os cards
  destacam progresso e previsão.

## 5. Código

- `CommandStatus` (o status do comando, que estava copiado em 7 componentes), `Stat` e os formatadores
  (`hours1`, `usd`) num lugar só.
- Saíram o catálogo de hunts por pedra (`lib/hunts.ts`), a tabela de gemas por pedra do `GemsCard` (virou
  `PlanCard`, só o foco XP e o plano) e o diagnóstico de abas da página de vendas.
