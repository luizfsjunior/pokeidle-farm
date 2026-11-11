# 0003 — Supabase como intermediário entre painel e worker

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O painel fica na Vercel e o worker num VPS ou na máquina local. Os dois precisam conversar, e o painel precisa de autenticação.

## Decisão

Os dois falam só com o Supabase:
- O painel usa Supabase Auth (Google), e o RLS libera as linhas só para o dono.
- O worker usa a `service_role key`, guardada apenas no `.env` do lugar onde roda.
- Comandos vão pela tabela `commands`, com o Supabase Realtime avisando o worker. Estado e métricas vão para tabelas próprias.

## Consequências

- O worker não expõe porta, API nem HTTPS no VPS, o que diminui a superfície de ataque.
- Trocar o worker de lugar (local ↔ droplet) não exige mudar o painel.
- Depende do plano grátis do Supabase. Conferir os limites de Realtime e de armazenamento quando os eventos crescerem.

## Alternativas consideradas

- **FastAPI no droplet + painel chamando direto:** exige expor porta, configurar TLS e escrever auth própria.
- **Fila (Redis):** é mais uma peça para manter, sem ganho nesse volume.
