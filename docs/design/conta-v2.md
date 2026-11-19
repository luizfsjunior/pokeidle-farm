# Conta v2: estado ao vivo, inventário, ações confirmadas e uma conta que não fica parada

Rascunho de 18 e 19/11, ainda só desenho. O painel tem que servir para farmar sem abrir o jogo, e hoje ele mostra
resultado de farm mas não deixa operar a conta. Este documento junta o que apareceu nos diagnósticos desses dias e o
que muda no worker, no banco e no painel.

## O que aconteceu

- **18/11, 11:40 às 11:42, luizfsjunior_1.** Doze trocas de equipe pelo painel terminaram "feitas", mas o jogo recusou
  todas, uma a uma, com o aviso "acesse o Depot no Centro Pokemon de Cerulean". O worker marca "feito" quando envia,
  sem ler a resposta. O painel mostrou a troca e depois voltou atrás.
- **18/11, 12:07, luizfsjunior.** A conexão ficou aberta e muda por 4 h 30. Nada percebeu.
- **18/11, 16:37 até 19/11, 06:13, luizfsjunior_1.** Na Brave Steelix, o Venusaur gastava ~50 poções a cada 30 s.
  1. O restock bateu o teto de 50 mil de ouro por hora (`max_gold_per_hour`) e passou a registrar "sem_ouro", com
     30 milhões de ouro na conta.
  2. Sem poção nem revive, a equipe inteira morreu e a conta perdeu 60 mil de XP. O jogo desligou a caça automática
     (`autoHuntSemItens`) e deixou o último pokémon da troca, um Magikarp, como ativo.
  3. A conta ficou 13 h sem abater. Na volta da conexão, às 06:13, repetiu tudo e perdeu mais 127 mil de XP.

## 1. Três camadas de dados

1. **Estado ao vivo.** Uma linha por conta, gravada a cada mudança (1 a 2 s) e assinada pelo Realtime.
   - Guarda: o que a conta está fazendo (caçando, curando, no Pokécenter, capturando, desconectada, "muda há N min"),
     a hunt, o ativo e a vida dele, o último abate, o plugin que está no controle e os alertas abertos.
2. **Inventário.**
   - Coleção completa, uma linha por pokémon. O depot entra junto e é lido quando o worker passa no Depot.
   - Mochila: item e quantidade.
   - Esses dados substituem os recortes de hoje (equipe, os 24 mais fortes e os shinies).
3. **Histórico enxuto.** Somas por hora (`metric_hourly`) e só os eventos que contam história: captura, shiny, nível,
   evolução, venda, erro, aviso do jogo e resultado de comando. O evento cru fica poucos dias
   (`retencao-eventos.md`).

## 2. Ações: feito quer dizer que o jogo confirmou

- O comando só fica "feito" quando o estado que volta do jogo mostra o efeito pedido. Se vier um `aviso`, o comando
  falha com o texto do jogo.
- O texto dos avisos (`battle.aviso`) vai para o evento. Hoje o worker só grava o tipo.
- **A ação manual tem prioridade.** Enquanto um comando do painel mexe na equipe ou na hunt, os plugins que mexem
  nisso pausam, e o painel mostra a pausa.
- **O painel mostra "pendente"** até a confirmação, em vez de chutar o resultado.

## 3. Equipe montada no painel, aplicada numa ida só

- A tela "Montar equipe" mostra 5 vagas e o ativo ao lado da coleção completa. O rascunho fica salvo no banco, e o
  painel mostra o que muda.
- "Aplicar" vira um comando só. O worker:
  1. pausa os plugins e guarda a hunt atual;
  2. vai ao Pokécenter de Cerulean e abre o Depot;
  3. faz as trocas na ordem certa, respeitando o intervalo do jogo;
  4. confere a equipe final e lê o depot de passagem;
  5. define o ativo, volta para a hunt e retoma os plugins.
- O painel acompanha passo a passo. Se algo falhar no meio, o worker volta para a hunt e diz o que entrou e o que não.
- Tornar ativo continua instantâneo, porque o jogo aceita fora do Depot.
- **Levantado no código do jogo (19/11):**
  - o Depot não é um lugar para onde se anda: é um botão do Pokécenter, e `team.move` só funciona com a conta no
    Pokécenter;
  - `centro.ir` leva da hunt ao Pokécenter de Cerulean, e `hunt.select` volta;
  - a lista do depot já vem inteira no estado (`estado.pokemons` com `slot` nulo), sem páginas.

  O "Aplicar" fica assim: `centro.ir`, esperar o campo do centro, fazer os `team.move`, o `team.active` e o
  `hunt.select` da hunt de antes.

## 4. Gasto do restock por orçamento, não por teto fixo

O teto de 50 mil por hora vale para tudo o que se compra: poções, revives e pokébolas. Numa hunt dura, ou com captura
ligada, ele estoura em minutos, e o que falta primeiro é o que mantém a conta viva.

- **Sobrevivência primeiro.** Poções e revives não entram no teto por hora. O limite deles é a reserva mínima de ouro.
- **Pokébolas por orçamento de captura.** O alvo de captura diz quanto vale gastar, pelo preço por captura que a
  Pokédex já calcula. Quando a captura não tem alvo, as bolas ficam com um teto próprio por hora.
- **Gasto contra renda.** O restock compara o ouro gasto em consumíveis com o ouro que a hunt rende na mesma janela.
  - Se a sobrevivência custa mais do que a hunt rende por um tempo (o caso da Brave Steelix), o problema é a hunt.
    O restock abre um alerta e a vigia (seção 5) troca de hunt, em vez de seguir pagando ou parar de comprar.
- **Motivo certo no aviso.** "sem_ouro" só quando falta ouro de verdade. Quando for o teto, "teto por hora atingido",
  com o valor.
- **No painel.** O card de restock mostra, por hora: o gasto em sobrevivência, o gasto em bolas, a renda da hunt e
  quanto do teto já foi usado.

## 5. Uma conta que não fica parada (vigia)

O worker percebe que uma conta parou e resolve, nesta ordem:

| Sinal | O que faz |
|---|---|
| Nenhuma mensagem do jogo por N min com a conexão aberta | reconecta |
| `autoHuntSemItens` ou estoque de poção/revive abaixo do mínimo | compra (sobrevivência fora do teto) e religa a caça |
| Ativo fora do previsto (nível muito abaixo do alvo, morto) | põe de volta o ativo certo |
| A equipe morre duas vezes na mesma hunt em pouco tempo | troca para a última hunt segura e marca a outra como perigosa para aquele ativo |
| Nenhum abate por N min com tudo certo | alerta no painel |

Cada ação da vigia vira um evento e aparece no estado ao vivo, para o painel dizer o que aconteceu durante a noite.

## 6. Escolha de hunt que considera sobrevivência

O foco XP escolhe a hunt por XP/h e gemas/h. Ele passa também a descartar a hunt onde o ativo não aguenta:

- consumo de poção alto demais ou morte recente naquele par ativo × hunt (medido, não simulado);
- tipos desfavoráveis contra o ativo (a tabela de tipos que a ficha já usa), como critério de desempate.

## 7. Revisão do que fica guardado (o Supabase não pode encher)

O plano grátis tem 0,5 GB. Em 18/11 o banco passou disso: a tabela `events` era 96% do banco, e a maior parte era
evento que nada lia. Em 19/11, às 09:20, ele já estava em 378 MB de novo: com o worker ainda sem rebuild, os
`state.patch` somavam 144 MB por dia.

**Regra para qualquer tabela nova:** antes de criar, dizer quantas linhas por dia ela ganha, quanto ocupa e quem lê.
O que ninguém lê não se grava. O que muda o tempo todo é *atualizado* (upsert numa linha), não *acrescentado*.

### Orçamento por tabela (4 contas)

| Tabela | Como cresce | Guarda | Teto |
|---|---|---|---|
| `events` | ~40 mil linhas/dia sem `state.patch` (abates são 25 MB/dia) | abates, capturas e consumo: 4 dias; ruído: 2 dias; o resto: 30 dias | 200 MB |
| `metric_hourly` | ~750 linhas/dia | tudo (é o histórico de verdade) | 30 MB/ano |
| `market_prices` / `market_asks` | ~2 mil linhas/dia | 30 dias | 10 MB |
| `commands` | ~30 linhas/dia | 30 dias (a criar) | 1 MB |
| `account_profile` | 1 linha por conta, atualizada | a linha atual | 1 MB |
| catálogo do jogo (`game_*`) | substituído a cada versão do jogo | a versão atual | 10 MB |
| **novas:** estado ao vivo | 1 linha por conta, atualizada | a linha atual | < 1 MB |
| **novas:** coleção / mochila | 1 linha por pokémon ou item, atualizada; sai quando o pokémon sai | o estado atual | 5 MB |

O total previsto fica abaixo de 300 MB, com folga para crescer.

### Cuidados

- **O evento cru é o que mais enche.** Antes de gravar um tipo novo de evento por padrão, ele entra em
  `NOT_PERSISTED` ou numa retenção curta, até alguém precisar dele.
- **Apagar não diminui o arquivo.** O espaço apagado é reusado, mas o tamanho cobrado só cai com uma reescrita
  (`VACUUM FULL` ou `CLUSTER`). Com retenção diária, o banco se estabiliza sem reescrita. Reescrever só quando o tamanho
  já tiver passado do limite.
- **Realtime não guarda nada,** mas cada atualização gera WAL. Por isso o estado ao vivo junta as mudanças em 1 a 2 s.
- **Vigiar o tamanho.** Um cartão no painel mostra o tamanho do banco e das 5 maiores tabelas, com alerta a partir
  de 400 MB. A limpeza diária grava quanto apagou.

## Ordem sugerida

0. Rebuild do worker para parar o `state.patch` (seção 7).
1. Comando confirmado pelo jogo e texto dos avisos (seção 2). É pequeno e corrige o "feito que não fez".
2. Orçamento do restock e a vigia (seções 4 e 5). Evitam outra noite parada.
3. Levantar no código do jogo as mensagens do Depot.
4. Estado ao vivo (seção 1.1).
5. Coleção completa, mochila e depot (seção 1.2).
6. Equipe montada no painel (seção 3).
7. Escolha de hunt com sobrevivência (seção 6).
