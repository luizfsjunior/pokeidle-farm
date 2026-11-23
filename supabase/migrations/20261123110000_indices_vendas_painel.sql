-- As leituras de vendas do painel (web/app/(painel)/economia/sales.ts) filtram events por um campo do
-- `data` (`action` das ações de Mercado, `aba` das respostas do Mercado). Sem índice nesse campo, o Postgres
-- varria os ~90 mil action.* de 30 dias e passava dos 8 s do papel authenticated (39 s medidos em 23/11):
-- erro 500 no painel. Com os índices: 72 ms e 285 ms.
-- Os dois já foram criados à mão (concurrently) no projeto em 23/11; aqui o `if not exists` não faz nada.
create index if not exists events_action_by_action on public.events
  ((data->>'action'), account_id, received_at desc)
  where type in ('action.sent', 'action.blocked', 'action.failed');

create index if not exists events_market_reply_by_aba on public.events
  ((data->>'aba'), account_id, received_at desc)
  where type = 'market.reply';
