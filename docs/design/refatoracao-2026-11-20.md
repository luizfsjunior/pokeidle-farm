# Refatoração de 20/11/2026: treino que não mata, um dono da hunt e o painel arrumado

Origem: revisão de 20/11 (pedido: "tá ficando uma gambiarra"). Os problemas vieram dos eventos reais da
`luizfsjunior_1` e da `luizfsjunior`, e de uma passada pela interface no navegador. O usuário pediu para escrever
tudo e implementar direto. As decisões que ele não respondeu seguem os padrões da seção 6.

## 1. O que aconteceu (evidência)

- **Loop de revive (13:50–14:45, `_1`)**: o `team_train` pôs como ativo um Totodile nv 20 que tinha acabado de
  entrar na equipe. A conta estava no Totodile nv 260: morte a cada 1–2 s, o jogo revive sozinho (`battle.revive`)
  e o `restock` comprou 11 revives (6.600 de ouro) a cada ~15 s. Foi ~1,4 M de ouro na hora. A vigia não viu,
  porque só conta morte que leva ao Pokécenter.
- **A hunt não trocava**: morrendo sem parar, a trava de combate (`centroLivreEm`) nunca abre e o `hunt.select`
  nunca sai, nem o manual. Ao devolver o ativo forte (14:45:05), a troca saiu em 17 s.
- **Plano de XP de 24 min**: o primeiro `gems.plan` depois do `focus.set` das 13:52 só saiu às 14:16. Ele roda o
  simulador para todas as hunts segurando o lock do plugin, e os eventos (troca de ativo, level up) ficam
  esperando. O cache do simulador é por nível exato do ativo, então cada level up re-simula tudo, para 4 contas
  numa máquina pequena.
- **XP/h absurdo para ativo fraco**: com o ativo nv 20, Rhydon nv 100 apareceu a 9,2 M XP/h. O ritmo medido perto
  do teto não era projetado para baixo (`PaceBook.projected`) e a lista não olha se o ativo sobrevive.
- **`luizfsjunior` (pessoal)**: Charizard 204 em Jynx, 175 revives em 15 min, −127 mil de ouro/h no dia.
- **Travas**: uma por ação no gateway (`holds[action]`). A segunda trava apaga a primeira, e soltar uma apaga a
  outra.
- **Pokédex**: o `CaptureForm` sem `key` guardava a hunt da espécie anterior (`capture.start` do Totodile na
  hunt `larvitar`, 03:16).

## 2. Fase 0: correções urgentes (worker e um bug do painel)

### 2.1 Projeção de ritmo para baixo
`PaceBook.projected`: o atalho "perto do teto, não projeta" só vale quando o ativo de agora é **mais forte** que o
medido (`level_now >= lvl0`). Para um ativo mais fraco, o ritmo sempre cai pelo fator de dano.

### 2.2 Hunt que o ativo aguenta (foco XP)
`GemsConfig.max_over_active` (padrão 10): o foco XP só considera hunts de nível ≤ nível do pokémon planejado + 10.
Também ficam de fora as hunts marcadas como perigosas para esse pokémon (2.4). O simulador recebe o mesmo teto, o
que também encurta o cálculo.

`shortcut:` regra por nível, não por sobrevivência simulada. Para algo mais fino, o simulador de combate precisaria
devolver o dano tomado por abate.

### 2.3 Plano sem travar o plugin
- Cache do simulador por **faixa de 10 níveis** do pokémon (`level // 10`): o level up não re-simula tudo.
  `shortcut:` dentro da faixa o ritmo é o do nível em que a faixa foi simulada (erro pequeno, no máximo 10 níveis).
- O plano passa a ser pedido (`_request_plan`), não chamado no meio do evento: uma tarefa por vez, que aquece o
  cache do simulador **fora do lock** e só depois planeja com o lock. Pedidos que chegam enquanto ela roda viram um
  só (o motivo mais recente). Abates, `hunt.changed` e erros continuam sendo tratados na hora.

### 2.4 Vigia: tempestade de revives
O `watchdog` conta `battle.revive`. Com `revive_storm` (padrão 8) revives em `revive_window_s` (padrão 180 s):
1. grava `watchdog.revive_storm` {hunt_slug, active_id, revives};
2. marca o par (pokémon, hunt) como perigoso por `danger_ttl_s` (padrão 6 h) em `StateView.danger`;
3. se o ativo não é o mais forte da equipe, devolve o ativo para o mais forte (`team.active`): é o que para as
   mortes, porque a troca de ativo sai mesmo em combate. Vai junto a nota `watchdog.restore_strongest`.

Uma tempestade por par a cada `revive_window_s`.

### 2.5 Treino da equipe: o foco planeja para quem vai treinar
- O `team_train` escolhe o próximo a treinar (o mais fraco abaixo do alvo, como hoje) e publica em
  `StateView.train_target` (o id dele). O `gems` (foco XP) planeja para esse pokémon, não para o ativo.
- O `team_train` só troca o ativo para ele **quando a hunt atual é segura para ele** (nível da hunt ≤ nível dele +
  `max_over_active`, e o par fora de `danger`). Senão espera o foco levar a conta para uma hunt boa. Sem o foco XP
  ligado, troca como hoje.
- Se o `watchdog` devolveu o ativo forte, o par (fraco, hunt) fica perigoso. O plano escolhe outra hunt, e o
  `team_train` só troca de novo quando a conta estiver nela.
- Falha ao trocar (sem confirmação em `confirm_s`): espera 1, 2, 4… até 30 min antes de tentar de novo.
- A equipe do `StateView.team` passa a trazer o perfil inteiro de cada membro (ivs, quality, potencia, shiny), para
  o simulador montar o lutador.

### 2.6 Travas com vários donos
`ActionGateway.holds`: ação → {dono: (até, rótulo)}. `held_by_other` bloqueia se houver trava válida de **outro**
dono (o pedido com o mesmo rótulo de uma delas passa, como hoje). `release(owner)` só solta as do dono. O
`team.apply` deixa de salvar e restaurar o dicionário inteiro: põe e solta a trava dele.

### 2.7 Pokédex
`CaptureForm` com `key` pela espécie e pela conta (`PokedexGrid.tsx`).

## 3. Fase 1: modo da conta e desvios

Modelo: **um modo base** (o que a conta faz sozinha) e **no máximo um desvio** temporário por cima, que termina e
devolve ao modo base.

- **Modos base** (`focus.set`): XP, Ouro e drop, Rank. "Gemas" continua só para quem já está nele.
- **Opções do modo**, no mesmo formulário e no mesmo comando:
  - `catch_all` (antes era o foco "Captura"): jogar a melhor bola que se paga em todo selvagem. Vale em qualquer
    modo. É o `restock.focus = "capture"`.
  - `train` (só no XP): `{enabled, target_level}` liga ou desliga o `team_train`.
- **Desvios** (um de cada vez): capturar uma espécie (`capture.start`) e hunt manual por X h (`hunt.select`).
  Começar um desliga o outro (`hunt.select` agora para a captura também).
- O foco "Captura" sai da lista. Uma config antiga com `restock.focus = "capture"` aparece como "Ouro e drop + bola
  em tudo".

## 4. Fase 2: painel

### 4.1 Agora
- **Card "Fazendo agora"** com: Modo (com as opções), Desvio (captura ou hunt manual, com o que falta e "volta ao
  modo X depois"), Hunt atual e Treino (quem treina, nível, quantos já no alvo).
- O plano mostra **há quanto tempo** foi feito e, se a conta não está na hunt alvo, **por quê** (desvio segurando,
  trava de combate, hunt perigosa). Troca o "Ativo:/Ensaio:" por "Agindo"/"Em ensaio".
- **Alertas** da conta (também na visão geral): ouro líquido negativo na última hora, tempestade de revive, sem
  abates, hunt perigosa.
- Ping/Reconectar/Curar/Desligar vão para um menu "⋯" no cabeçalho.

### 4.2 Pokémons
- Uma lista só: tira o card "Equipe" repetido, o card "Coleção" de números (vira uma linha de resumo) e o "Mais fortes
  fora da equipe". "Coleção" passa a ser só o lugar (pokémons guardados). O painel da lista se chama "Pokémons".
- **Dois jeitos de ver**: grade (como hoje) e **tabela de comparação** com colunas ordenáveis: Tipos, Qualidade,
  Nota, IV total, os 6 IVs, os 6 stats de combate (quando o jogo manda), Nível, Potência. A ordem inicial é Qualidade,
  depois Nota. O melhor de cada coluna (na lista filtrada) fica destacado.
- **Montar equipe**:
  - as vagas ficam **fixas no topo** enquanto a lista rola;
  - cada vaga mostra tipos, Qualidade, Nota e IV total, e a soma da equipe montada contra a de agora;
  - clicar num pokémon **abre a ficha**, com "Pôr na equipe" / "Tirar" (escolher e analisar são coisas separadas);
    na tabela, uma coluna com botão de pôr ou tirar;
  - **Sugerir**: preenche as vagas com os 5 melhores por Qualidade e depois Nota (um por espécie), mantendo o ativo;
  - ★ / setas / × viram botões com texto e tamanho de toque;
  - filtro por tipo e busca valem na montagem.
- **Seleção em lote** (guardar na Coleção / mandar para o Depot) na tabela.
- Mochila: ícones que faltam, rótulo "vale ~2 gemas" nas pedras, e o que o `restock` mantém (mínimo e alvo).

### 4.3 Ajustes
Lista de plugins com nome legível e ligar/desligar. O JSON vai para um "Avançado" fechado.

## 5. Fase 3: loja e Mercado

- **Loja (NPC)** na aba Itens: comprar à mão (`shop.buy`, já no worker) bolas e consumíveis com o preço do catálogo
  e o ouro de agora; editar as regras do `restock` (mínimo e alvo por item) num formulário; gasto do dia por item.
- **Mercado**: anúncios abertos da conta, cancelar (`market.cancel`) e anunciar à mão (`market.sell`: item,
  quantidade, preço em gemas), com o menor anúncio e a fila do item ao lado. Só para itens que o `seller` já
  entende (o protocolo de `market.criar`/`cancelar` está em protocolo.md).
- Venda de pokémon em lote: o jogo só tem `shop.sellAllPokemons` (o Depot inteiro). Fica "marcar em lote para
  Coleção/Depot" + "vender o Depot".

## 6. Decisões tomadas sem resposta (o usuário pediu para seguir)

| Pergunta | Escolha |
|---|---|
| Loja e Mercado entram? | Sim, na fase 3 |
| Sugerir equipe | Sim, por Qualidade e Nota, um por espécie |
| Venda em lote | Só o que o protocolo tem (Depot inteiro) |
| Ordem | Fase 0 → 1 → 2 → 3, commit por etapa |
| Colunas da comparação | Qualidade, Nota, IV, stats e tipo (resposta do usuário) |
