-- Banco passou de 0,5 GB (limite do plano grátis) em 18/11: a tabela events tinha 646 MB, e 400 MB
-- eram `state.patch`, que nada lê do banco (o worker deixa de gravar). Ver docs/design/retencao-eventos.md.
--
-- 1. apaga os state.patch;
-- 2. prune_events() todo dia pelo pg_cron. As somas por hora (metric_hourly, de onde saem as hunts de
--    24 h, 7 e 30 dias) já ficam guardadas; o evento cru só serve às janelas curtas:
--    - os volumosos (abates, tentativas de captura, consumo de item: ~50 MB/dia com 4 contas): 4 dias;
--    - o ruído (curas, fugas, ações, desconhecidos): 2 dias;
--    - o resto (capturas, níveis, vendas, planos): 30 dias;
-- 3. reescreve a tabela (CLUSTER) para o espaço voltar e o tamanho do banco cair de verdade.

-- a primeira passada apaga ~280 mil linhas e reescreve ~650 MB: passa do limite de 2 min do statement
-- (a primeira tentativa, em 18/11, caiu por timeout e nada foi aplicado). Vale só para esta transação.
set local statement_timeout = 0;
set local lock_timeout = '60s';

delete from public.events where type = 'state.patch';

create or replace function public.prune_events()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_noise bigint;
  v_old bigint;
begin
  delete from public.events
   where (type in ('state.patch', 'battle.cura', 'wild_fled', 'action.sent', 'unknown')
          and received_at < now() - interval '2 days')
      or (type in ('kill', 'capture_attempt', 'item.consumed')
          and received_at < now() - interval '4 days');
  get diagnostics v_noise = row_count;
  delete from public.events where received_at < now() - interval '30 days';
  get diagnostics v_old = row_count;
  return v_noise + v_old;
end;
$$;

revoke all on function public.prune_events() from public, anon, authenticated;
grant execute on function public.prune_events() to service_role;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('events-prune', '23 4 * * *', 'select public.prune_events()');
  end if;
end;
$$;

select public.prune_events();

-- o DELETE só marca o espaço como livre; o CLUSTER reescreve a tabela e devolve o espaço ao disco
cluster public.events using events_account_time;
analyze public.events;
