# 0010 — Supabase desde o início do desenvolvimento

- **Status:** Aceita
- **Data:** 2026-11-11
- **Complementa:** [0003](0003-supabase-como-intermediario.md)

## Contexto

O Supabase é o intermediário entre o painel e o worker ([ADR 0003](0003-supabase-como-intermediario.md)). Faltava decidir se ele entraria já na fase 2 ou só na fase 4, com SQLite local até lá.

## Decisão

Usar o **Supabase desde a fase 2**, num projeto do plano grátis. O schema fica versionado em `supabase/migrations/` e é aplicado com a Supabase CLI.

## Consequências

- O worker grava eventos brutos no mesmo lugar desde o primeiro dia, sem migração de dados depois.
- O schema e as policies de RLS evoluem junto com o código, desde o começo.
- O desenvolvimento depende de internet e dos limites do plano grátis. Ficar de olho no armazenamento de `events`, que cresce rápido.
- Os testes automatizados podem rodar contra um Supabase local (`supabase start`, com Docker), para não sujar o projeto real.

## Alternativas consideradas

- **SQLite local até a fase 4:** começo mais leve, mas exigiria migrar o schema e os dados, e escrever a camada de acesso duas vezes.
