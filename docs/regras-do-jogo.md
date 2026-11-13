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

## Login e sessão (seções 4, 8 e 9)

- Login por e-mail e senha, Google ou Discord.
- Cadastro, login e "Esqueci minha senha" passam pelo Cloudflare Turnstile (anti-robô).
- O token da sessão fica no localStorage do navegador.

## Mercado (seção 13)

- Retenção de 2 minutos depois de anunciar ou mudar o preço.
- Os pedidos de compra que chegam nos 3 primeiros segundos depois da retenção entram num sorteio.
- Comissão: 15% em item e 7,5–13% em pokémon (vendas em Gemas); 15% em vendas por ouro.
- Anúncio de pokémon: 100.000 Coins por dia.
- Até 20 anúncios abertos por conta.

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

⚠️ A faixa 1,6–1,7 não aparece nos Termos, e as chances listadas já somam 100%.

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

## Implicações para o código

- O `RateLimiter` é obrigatório, não opcional. O servidor também limita rajadas por conta.
- Nunca mais de 4 contas configuradas no total, contando a conta pessoal.
- O sniper de Mercado, se existir, respeita a retenção e o sorteio, sem tentar contornar a janela.
- Comportamento estranho do jogo (possível bug): o worker para a estratégia e registra o evento. O caminho é reportar no Bug Bounty, não explorar.
