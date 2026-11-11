# 0001 — Registrar decisões em ADRs

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O projeto vai ser construído aos poucos, e várias escolhas (hospedagem, auth, protocolo) dependem de informações que mudam, como preços e termos do jogo. Sem registro, fica difícil lembrar por que algo foi decidido.

## Decisão

Cada decisão relevante vira um arquivo em `docs/decisions/NNNN-titulo.md`, com Status, Data, Contexto, Decisão, Consequências e Alternativas. Os status possíveis são Proposta, Aceita, Substituída ou Rejeitada. Uma decisão substituída não é apagada: o arquivo aponta para a que a substituiu.

## Consequências

- O histórico fica no repositório, junto do código.
- Toda decisão nova também entra na tabela do README.
