-- O painel soma o ouro gasto nas compras automáticas das últimas 24 h (web/lib/shop.ts, loadSpend) lendo os
-- restock.bought e capture_target.bought de cada conta. Sem índice próprio, o Postgres varria todos os eventos do
-- dia da conta: 2,3 s por conta, e a Economia com todas as contas faz uma por conta ao mesmo tempo (timeout em
-- 23/11). Com o índice: 8 ms. Já criado à mão (concurrently) no projeto em 23/11; aqui o `if not exists` não faz nada.
create index if not exists events_purchases_by_account on public.events (account_id, received_at desc)
  where type in ('restock.bought', 'capture_target.bought');
