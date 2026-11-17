# 0014 — A conta pessoal também roda no worker

- **Status:** Aceita
- **Data:** 2026-11-17
- **Altera:** [0006](0006-contas.md), no ponto "a conta pessoal não entra no worker"

## Contexto

A 0006 deixou a conta pessoal (`luizfsjunior`) fora do worker, para jogar na mão em casa. O dono decidiu subir ela
também, para farmar XP 24/7 como as outras.

## Decisão

- As 4 contas rodam no worker, todas com `role = farm` (o worker só roda esse role). O limite do worker passa de 3
  para 4 (`MAX_FARM_ACCOUNTS`), que é o limite dos termos por pessoa.
- Na conta principal: foco XP, `seller` desligado (não vende nada dela).
- Para jogar na mão: desligar a conta no painel, jogar, fechar a aba sem "Sair" e ligar de novo.

## Consequências

- O total continua em 4 contas por pessoa. **Nunca** criar uma 5ª, nem de teste.
- A rede do proxy fica no limite (4 contas conectadas); nada mais pode conectar por aquele IP.
- Se o jogo barrar o IP do proxy ou as contas automatizadas, a principal cai junto: esse risco foi aceito.
