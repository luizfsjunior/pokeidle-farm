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

## Implicações para o código

- O `RateLimiter` é obrigatório, não opcional.
- Nunca mais de 4 contas configuradas no total, contando a conta pessoal.
- O sniper de Mercado, se existir, respeita a retenção e o sorteio, sem tentar contornar a janela.
- Comportamento estranho do jogo (possível bug): o worker para a estratégia e registra o evento. O caminho é reportar no Bug Bounty, não explorar.
