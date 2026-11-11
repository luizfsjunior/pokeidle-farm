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

Todos os sorteios acontecem no servidor. O cliente não influencia captura, shiny, potência nem drop. Shiny: 1 em 24.000.

## Implicações para o código

- O `RateLimiter` é obrigatório, não opcional.
- Nunca mais de 4 contas configuradas no total, contando a conta pessoal.
- O sniper de Mercado, se existir, respeita a retenção e o sorteio, sem tentar contornar a janela.
- Comportamento estranho do jogo (possível bug): o worker para a estratégia e registra o evento. O caminho é reportar no Bug Bounty, não explorar.
