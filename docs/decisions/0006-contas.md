# 0006 — 4 contas: 3 de farm + 1 pessoal

- **Status:** Aceita (forma de login alterada pela [0007](0007-contas-farm-email-senha.md))
- **Data:** 2026-11-11

## Contexto

Os termos permitem até 4 contas por pessoa, somando todas as redes e aparelhos. Cada rede também aceita até 4 contas conectadas ao mesmo tempo.

## Decisão

- 3 contas de farm, rodando no worker (droplet).
- 1 conta pessoal, para jogar na mão e evoluir pokémons no navegador de casa. Ela não entra no worker.
- ~~Cada conta tem a própria conta Google.~~ Substituído pela [0007](0007-contas-farm-email-senha.md): as contas de farm usam e-mail e senha, e a pessoal usa Google.

## Consequências

- O total da pessoa fica exatamente no limite (4). **Nunca** criar uma 5ª conta, nem de teste.
- Ficam 3 contas na rede do droplet e 1 na rede de casa, dentro do limite por rede.
- Passar valor entre as próprias contas só é permitido pelo Mercado da Comunidade.
