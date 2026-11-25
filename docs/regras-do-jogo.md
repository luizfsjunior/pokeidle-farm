# Regras do jogo que afetam o projeto

Resumo dos Termos do pokeidle.io (versão de 2026-10-12, revisão de 2026-11-07), lido em 2026-11-11. Confira o original em https://pokeidle.io/terms antes de mudanças grandes, porque os termos podem mudar.

## Automação (seção 5)

Automações são permitidas, no jogo e no Mercado. Elas seguem as mesmas regras de quem joga na mão e **não podem**:
- explorar falhas;
- burlar limites do jogo (contas por pessoa e por rede, travas e retenções do Mercado);
- sobrecarregar o servidor.

Automação que descumpre isso leva a suspensão de 48 h, que pode virar banimento de 7, 15 ou 30 dias, ou permanente (seção 6, item 6).

## Contas (seção 5, "Multicontas")

- Até **4 contas por pessoa**, somando todas as redes e aparelhos.
- Cada rede: até 4 contas criadas e até 4 conectadas ao mesmo tempo.
- A detecção usa a rede e um identificador do navegador guardado no localStorage.
- Mais de 4 contas: banimento permanente de todas e saques de Gemas travados.
- Cadastro por e-mail (testado em 16/11): só aceita `@gmail.com`, `@live.com`, `@yahoo.com` e `@yahoo.com.br`, e
  normaliza o endereço (`+alias` e pontos do Gmail contam como o mesmo e-mail). Cada conta precisa de uma caixa de
  verdade. O Google limita quantas contas um celular verifica ("dispositivo usado muitas vezes"): espere uns dias ou
  use Yahoo. Desde então (guia de 19/11): conta nova **recusa** e-mail com `+` e e-mail descartável, e o formulário
  recusa o ponto antes do `@` no Gmail.
- **Vincular contas** (Ficha do Treinador → Vincular contas, ou `pokeidle.io/vincular`): código de 6 dígitos no
  e-mail da outra conta, válido por 15 min. O vínculo é **para sempre**; a vaga de uma conta vinculada que for
  excluída não volta.
- O limite de 4 por rede vale para rede compartilhada e a equipe não libera mais. No PvP Ranqueado, partida entre
  contas da mesma rede vale 0 PR.
- **Uma sessão por conta**: abrir em outro aparelho pausa a antiga ("Conta aberta em outro lugar"). Voltando em até
  90 s, a conta continua de onde estava; depois disso, entra no Centro no próximo login, sem perder XP.

## Login e sessão (seções 4, 8 e 9)

- Login por e-mail e senha, Google ou Discord.
- Cadastro, login e "Esqueci minha senha" passam pelo Cloudflare Turnstile (anti-robô).
- O token da sessão fica no localStorage do navegador.

## Mercado (seção 13)

- Retenção de 2 minutos depois de anunciar ou mudar o preço (somar unidades também reinicia).
- Os pedidos de compra que chegam nos 3 primeiros segundos depois da retenção entram num sorteio.
- Comissão (só do vendedor): 15% em Coins e 15% em item vendido em Gemas. Pokémon em Gemas paga **por faixa**, como
  imposto de renda: 13% até 500, 10% de 500 a 5.000 e 7,5% acima de 5.000 (2.000 gemas → recebe 1.785).
- Anúncio de pokémon: 100.000 Coins por dia, de 1 a 30 dias, pagos à vista; os dias não voltam se vender antes.
- Até 20 anúncios abertos por conta e até **10 pokémon** na vitrine ao mesmo tempo.
- **30 minutos** para anunciar de novo o mesmo item (ou pokémon tirado da vitrine) e entre duas mudanças de preço.
  Nos itens, a vitrine vai do menor preço ao maior e, no mesmo preço, quem anunciou antes vem primeiro.
- Diamante não se vende (desde 27/10). Mega Stone, Z-Move, AoE TM, Shiny Stone e Ovo Shiny: só os fragmentos.
  Drop de pokémon (Bug Wing, Fur) não entra. **Shiny só se vende em Gemas.**
- Compra em quantidade junta os anúncios mais baratos, até 500 por compra. Pokémon comprado vai para a Coleção.
- Venda cai numa caixa postal: entra no login ou em até 1 minuto, se já estiver dentro.

## Gemas (seção 12)

- Compra: US$ 0,01 por Gema. Recompra (saque): US$ 0,009 por Gema.
- Saque mínimo de 1.000 Gemas (US$ 9) e aprovação manual.
- As Gemas só entram no jogo por depósito de USDT. Para as contas de farm, a renda vem de vender no Mercado.

## Sorteios (seção 14)

Todos os sorteios acontecem no servidor. O cliente não influencia captura, shiny, potência nem drop. Nada pago muda as tabelas de potência, qualidade e IV. Implementado em [`worker/src/pokeidle_farm/sim/rolls.py`](../worker/src/pokeidle_farm/sim/rolls.py).

**Potência** (sorteada na captura):

| Potência | Chance | Bônus de atributos |
|---|---|---|
| 1 | 74,495% | +0% |
| 2 | 20% | +5% |
| 3 | 5% | +10% |
| 4 | 0,5% | +25% |
| 5 | 0,005% | +100% |

Exceções: o pokémon inicial nasce com P2, e os Mystery Eggs têm potência fixa (2, 3 ou 4).

**Qualidade** (multiplica os atributos): sorteada por faixa e, dentro da faixa, uniforme com 3 casas decimais.

| Faixa | Chance |
|---|---|
| 0,8–0,9 | 5% |
| 0,9–1,0 | 5% |
| 1,0–1,1 | 34,03846% |
| 1,1–1,2 | 20% |
| 1,2–1,3 / 1,3–1,4 / 1,4–1,5 | 10% cada |
| 1,5–1,6 | 5% |
| 1,7–1,8 | 0,67308% |
| exatamente 1,8 | 0,28846% |

A faixa 1,6–1,7 não existe: nenhum pokémon sorteado nasce nela (confirmado no guia "Entendendo o seu Pokémon" do
pokeidleguide.io, jogo 1.451.2). O inicial não é sorteado: nasce com qualidade 1,6 e IV 27 em cada stat (desde a v36).

**IVs:** HP, Ataque, Defesa, Sp. Atk, Sp. Def e Speed, cada um uniforme de 1 a 32 (soma de 6 a 192, média 99). Num shiny, os seis são sorteados de novo até a soma passar de 110. O lendário do Mystic Ticket tem qualidade ≥ 1,00 e soma de IV > 110.

**Shiny:** 1 em 24.000 por arremesso (o Shiny Secret Lure dobra a chance). Um shiny tem o triplo dos atributos da forma comum. Não há shiny nas hunts da Outland.

**Mercado:** só pode ser anunciado pokémon de nível ≥ 50 e "nota" ≥ 3,5. Shiny, P5, lendário e mítico entram em qualquer nível e nota. Os Termos não explicam como a nota é calculada.

## Da wiki do jogo (13/11/2026)

Resumo do que importa para o worker, tirado da wiki que o jogo publica (com os números do servidor). Não é cópia:
para o texto completo, veja a wiki dentro do jogo.

### Captura

- Uma tentativa por corpo: o selvagem derrubado fica 30 s no chão e, se a bola falha, o corpo some.
- A chance depende só do **estágio evolutivo** da espécie e da bola, igual em todas as regiões:

  | Bola (preço) | 1º de três | meio, ou 1º de dois | última, ou não evolui |
  |---|---|---|---|
  | Poke Ball ×1 (5) | 0,37% | 0,30% | 0,30% |
  | Great Ball ×2 (20) | 0,73% | 0,59% | 0,47% |
  | Super Ball ×3 (50) | 1,10% | 0,88% | 0,70% |
  | Ultra Ball ×4 (130) | 1,46% | 1,17% | 0,94% |
  | Beast Ball ×8 (só diamante) | 2,93% | 2,35% | 1,88% |

  Fórmula: `0,0075 × (eficiência / fator) × (1,4 − hpAtual/hpMáx)`, com fator 2,87 · 3,57 · 4,47 pelo estágio,
  entre 0,30% e 10%. O Capture Boost da Loja dobra. Magikarp (1º de dois) com Ultra Ball dá 1,17%, o que bate
  com a captura real de 12/11.
- **Lançar até Capturar** (`autoBallAteCapturar`) e **Lançar sem Parar** (`autoBallSemParar`), só VIP: uma bola
  por corpo, 1,2 s entre arremessos, sempre a primeira bola da lista com estoque. Ligar um desliga o outro.
  O "até capturar" **desliga na primeira captura** (de qualquer espécie) ou quando acabam as bolas. O "sem parar"
  continua ligado sem bolas e volta sozinho quando o estoque volta.

### Top Catch (ranking semanal)

- Conta **espécies diferentes capturadas com bola na semana** (na hunt, pela mão ou pelas automações, e na Arena
  Mística). Não contam evolução, ovo nem compra no Mercado. Repetir a espécie na semana não soma.
- A semana vai de domingo a sábado e **vira no sábado às 23h59 (Brasília)**. A Pokedex não zera, então a espécie
  conta de novo na semana seguinte.
- Prêmio pela posição final: 1º 50 💎, 2º–10º 20 💎, 11º–100º 5 💎 (só para usar na Loja). Desempate pelo nível do
  treinador e depois pela conta mais antiga. Quem fecha com 0 não recebe.
- O Mapa tem o filtro **"Top Catch: não capturados na semana"**, e a Pokedex tem o painel da semana.

### Mapa e hunts

- Cada região pede um nível mínimo do **treinador**: Kanto 1, Outland 150, Johto 200 (hunts de 30 em 30 até 470),
  Hoenn 500, Sinnoh 1.000, Unova 5.000, Kalos 10.000, Alola 25.000, Galar 40.000, Paldea 75.000. Área acima do
  nível fica trancada.
- Cada hunt mostra a "espécie principal" e o ouro/hora vem "das espécies que spawnam lá": a wiki dá a entender
  que uma hunt pode ter mais de uma espécie, mas não diz isso com todas as letras.
- Toda área tem o mesmo ritmo de ondas (os selvagens nascem em bandos, calibrados para o mesmo time limpar a onda
  no mesmo tempo); o que muda o abate/hora é a força do seu time contra aquela hunt.
- **Trocar de área**: depois de entrar, só dá para escolher outra 10 s depois; chegar até 10 s depois de trocar
  dano encontra a área vazia até completar o tempo.
- **Safari** (ticket que cai dos bosses e se negocia no Mercado): 60 min num mapa onde cada aparição é uma
  espécie sorteada entre 985. Captura normal com +15% de Capture Boost.

### Automação de fora do jogo

- Permitida pelos Termos (existe até uma extensão de automação oficial no Discord). As regras de conduta valem
  igual. O servidor limita rajadas de ações por segundo **por conta**.

## Dos guias do pokeidleguide.io (25/11/2026)

Resumo do que importa para o worker, tirado dos guias da comunidade em https://pokeidleguide.io/#guias (série do
Liang, atualizada entre 17 e 20/11 para o jogo 1.436 a 1.459). Não é cópia: para o texto completo, veja os guias. As
melhorias de lógica que saem daqui estão em [analise-guias-2026-11-25.md](analise-guias-2026-11-25.md).

### Combate e hunt

- **Ampliação de tipo na hunt**: ×4 vira ×5,5, ×2 vira ×2,5, ×0,5 vira ×0,33, ×0,25 vira ×0,17; neutro e imune
  não mudam. Os dois tipos do selvagem multiplicam antes da ampliação. Vale também no boss. (Bate com a ampliação
  1,5 de `model/combat.py`.)
- O selvagem tem HP ×5 e **dano ×1,8**; no mínimo 0,9 s entre golpes nossos e 1,4 s entre os dele.
- Recarga do golpe pelo poder: 15 → 10 s, 100 → 30 s, 600 → 60 s. Trocar o ativo pausa a recarga (não zera), e há
  3 s entre trocas. Curar no Centro não zera a recarga.
- **Desmaiar o time inteiro custa 10% do XP do nível atual do treinador** (com o Boost dos Atrasados, não custa).
  Desistir do combate também cobra XP. Ir ao Centro é grátis, mas pede 3 s sem trocar dano. Escape Rope: 1 💎.
- **Dia Sazonal**: às 18:00 (Brasília) um dos 18 tipos vira o do dia (nunca repete os 3 dias anteriores). Nas hunts
  do Mapa, Outland inclusive, quem é dele (pelo tipo do pokémon, não do golpe) tem ataque, defesa e vida ×2: bate
  ×2 em quem não é, apanha ×¼, e entre dois do tipo do dia fica ×½.
- **Shield do Novato**: todo treinador abaixo do nível do Boost dos Atrasados (mediana dos veteranos ativos,
  recalculada às 00:00; **1.160 em 17/11**) não sofre o lado ruim do dia: os selvagens do tipo do dia batem e
  aguentam como num dia comum, e os nossos do tipo do dia continuam com o ×2. Todas as nossas contas estão nele.
- **Prey** (Mochila → Prey): cartela diária que vira às 18:00, com a mesma hora do Dia Sazonal. A roletada do dia é
  grátis e revela 9 espécies de hunts do Mapa (sem Outland, lendários e míticos), um bônus (25% cada) e estrelas
  (1★ 55%, 2★ 30%, 3★ 10%, 4★ 4,5%, 5★ 0,5%). Por estrela: Dano +10%, Defensivo −10% no dano recebido, Capture Boost
  +2% (multiplica, até o teto de 10%) ou Spawn +1 selvagem da espécie por onda. Escolheu, ficou. Roletar de novo
  custa 1 milhão de Coins, dobrando a cada vez, por categoria. A 2ª cartela custa 100 💎, uma vez. Só nas hunts do
  Mapa.
- **Bestiário**: dano extra contra a tipagem de cada espécie abatida muitas vezes (25 mil: +0,05%; 150 mil:
  +0,15%; 500 mil: +0,5%); as espécies da tipagem somam. Pequeno; multiplica com Prey, Dia Sazonal e ginásios.
- **Pódio dos Ginásios**: +25% / +10% / +5% de dano com pokémon do tipo do ginásio, para o 1º, 2º e 3º.

### XP

- O XP por abate depende só do nível da hunt (hunt 200 paga 19.342, o que bate com `xp_model.py`).
- **Os bônus de XP se multiplicam** (VIP ×1,5 com XP Boost ×1,5 dá ×2,25). A única soma é dentro da guild (ranking
  + Boss Raid). VIP vale para treinador e pokémon; XP Boost Trainer só treinador; XP Boost Pokemon só pokémon.
- Boosts de graça: marcos do Top Catch (abaixo), Passe de Batalha, PvP Ranqueado (top 100) e Sacrifício.
- **Casa** e **Exp. Share** dão XP a mais a outro pokémon (25% a 100% na Casa, 5% no item), sem tirar do ativo.

### Top Catch: marcos da semana (desde 16/11)

Pagam na hora, uma vez por semana: 10 espécies → XP Boost Trainer 30 min; 25 → XP Boost Pokémon 30 min; 50 → os
dois por 1 h; 100 → Shiny Secret Lure 30 min; 150 / 200 / 300 → os três por 30 min / 1 h / 2 h; 400 → Lure 12 h;
600 → 1.000 Beast Balls e Lure 24 h. O boost soma ao tempo que já havia.

### Captura (complementa a seção da wiki)

- **Nível ao capturar (v31)**: numa hunt acima do Nv 100, o capturado nasce no teto da espécie pela cadeia
  evolutiva (de três: 20 · 40 · 100; de dois: 40 · 100; não evolui: 100). Até o Nv 100 nasce no nível da hunt.
- **Depot cheio (3.000 pokémon) trava a bola**, inclusive o auto-ball. A hunt continua dando XP e ouro, sem aviso
  de captura. Abre espaço: venda ao NPC, Oferenda, Sacrifício ou Mercado.
- Na Arena Mística, o lendário é uma bola só: 0,1% (Poke) a 0,5% (Beast), o dobro com Capture Boost.

### Pokémon

- Stat = (base + 2·IV) × nível/100 × qualidade^expoente × multiplicador (expoente 0,95 em HP e Speed, 0,8 nos
  outros). Multiplicadores: potência, shiny ×3, lendário/mítico ×4. A Nota (0 a 10) é do nascimento e só sobe ao
  evoluir (+0,1 no mínimo) ou refinar; o Poder ⚔ = nível × 10 × força, só ordena o placar.
- **Refino**: +1 num stat-base pago em pedra do tipo; o degrau N custa 500·(3N² − 3N + 1) pedras (+1: 500,
  +2: 3.500, +3: 9.500). Speed não refina. Refinar manda o pokémon para a Coleção.
- **Evolução**: nível e 1 pedra do tipo primário (exceções: Eevee pela pedra do destino, no Nv 80; pássaros
  Normal/Voador pela Feather Stone). Destinos de Hoenn em diante evoluem no 40 e no 100. Variantes de Outland não
  evoluem. Shiny pede a Shiny Stone do tipo (10 fragmentos) e é recusado se a próxima forma não tiver arte shiny.
  Dá para evoluir pela ficha, fora de campo (v41).
- **Drop de pedra**: cada selvagem solta a pedra de cada tipo dele, 0,2% / 0,35% / 0,5% por estágio (a variante de
  Outland conta como forma final).
- **Oferenda** (Mochila → Oferenda): até 5 pokémon do Depot viram uma pedra sorteada entre os tipos deles; a chance
  de sair pedra é pokémon ÷ 5 (5 = garantida), e quem tem dois tipos parte a casa ao meio. Shiny paga em Shiny
  Stone do tipo. Os oferecidos somem.
- **Sacrifício** (Mochila → Sacrifício): pokémon de Nota 3,5+ viram pontos (3,5 → 10, 4,0 → 25, 5,0 → 110,
  6,0 → 320, 7,0+ → 1.000). Barra de 1.000 pontos em 5 níveis: 50 → 8 h, 125 → 1 dia, 250 → 2,5 dias, 500 → 6 dias,
  1.000 → 14 dias de **+20% de XP** (treinador e pokémon). O resgate paga só o maior nível e zera a barra; o prazo
  soma até 30 dias e corre offline. O Osso do Sacrifício põe +100 pontos. Recusa equipe, lendário, inicial e quem
  está anunciado.
- **Venda ao NPC** (só pokémon, sem taxa): valorBase × (1 + nível/50, nível até 100) × qualidade × (shiny ? 10 : 1).
  A potência não conta. Quem evoluiu vende pela espécie em que foi capturado. O inicial e a Coleção não se vendem.

### Ouro

- Ouro por abate pelo nível do selvagem (1 → 41; 100 → 658; 1.000 → 2.624; 5.000 → 6.900), com o bônus de loot de
  15% embutido até o nível 25.000. O Loot Boost multiplica só esse bônus, não o ouro inteiro (vale pelos raros da
  Outland). Bate com `gold_per_kill` em `model/progression.py`.
- Poções: Small 60 HP / 50, Great 150 / 150, Ultra 400 / 400, Hyper 1.000 / 800, Ultimate 3.000 / 1.500. Revive 600
  (10% do HP), Max Revive 5.000.
- Mystery Eggs no Market: P2 20 mi (6 h), P3 120 mi (12 h), P4 250 mi (24 h).

### Outland (desde 16/11)

- **40 degraus**, do ×1 no nível 150 ao ×20 no 65.000 (10: 2.500 ×2,15; 20: 11.000 ×4,25; 30: 36.000 ×9). Mapa,
  pokémon, nível 150, XP e ouro iguais em todos; só muda a chance dos cinco raros. **O seletor não sobe sozinho.**
- Outland 1: Bronze Boss Token 1 em 10 mil; Fragmento de Chave, de Shiny Stone, de Bicicleta e **Osso do
  Sacrifício** 1 em 250 mil cada. O Loot Boost multiplica por cima. 10 fragmentos fazem um item no Professor
  Carvalho.
- As variantes de Outland (#2001 a #2058) não evoluem, não megaevoluem, nunca saem shiny e nascem no Nv 100.
- Do 150 ao 200 a Outland é a hunt mais alta alcançável; depois que Johto abre (200), serve só para os raros.

### Bosses

Bate com [design/foco-outland.md](design/foco-outland.md): 27 lendários (3 por região, Kanto Nv 300), nível fixo,
1 token por luta (perdido mesmo na derrota), dupla de prêmios que gira às 18:00, chance ×(região) até ×9 em Paldea,
Loot Boost não vale, cada pokémon que falta na equipe multiplica o dano tomado por 3. Repetição automática com 10 s
entre lutas.

## Implicações para o código

- O `RateLimiter` é obrigatório, não opcional. O servidor também limita rajadas por conta.
- Nunca mais de 4 contas configuradas no total, contando a conta pessoal.
- O sniper de Mercado, se existir, respeita a retenção e o sorteio, sem tentar contornar a janela.
- Comportamento estranho do jogo (possível bug): o worker para a estratégia e registra o evento. O caminho é reportar no Bug Bounty, não explorar.
- Contas novas: e-mail sem `+`, e o vínculo de contas é permanente (conferir o e-mail antes de pedir o código).
- Depot perto de 3.000 é falha silenciosa de captura: precisa de alerta e de esvaziamento.
- Desmaio custa XP do treinador: o foco XP precisa descontar o risco de morte, não só os abates.
- O modelo de dia sazonal precisa do Shield do Novato enquanto as contas estiverem abaixo do nível dos veteranos.
- Detalhes e prioridades em [analise-guias-2026-11-25.md](analise-guias-2026-11-25.md).
