-- Teste do histórico (account_history, archive_metric_hourly, hunt_summary com XP). Cria os próprios dados
-- e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values
  ('00000000-0000-0000-0000-0000000d1a01'), ('00000000-0000-0000-0000-0000000d1b02');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000d1ac001', '00000000-0000-0000-0000-0000000d1a01', 'hi-a', 'farm'),
  ('00000000-0000-0000-0000-00000d1bc001', '00000000-0000-0000-0000-0000000d1b02', 'hi-b', 'farm');

-- hoje (duas hunts e uma linha sem hunt), 3 dias atrás, 120 dias atrás (vai para o arquivo)
insert into public.metric_hourly (account_id, hour, hunt_slug, metric, value) values
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()), 'x', 'xp', 1000),
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()), 'y', 'xp', 500),
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()), 'x', 'active_minutes', 30),
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()), '', 'disconnects', 2),
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()), 'x', 'drops', 9), -- fora da lista
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()) - interval '3 days', 'x', 'kills', 40),
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()) - interval '120 days', 'x', 'kills', 77),
  ('00000000-0000-0000-0000-00000d1ac001', date_trunc('hour', now()) - interval '120 days', 'y', 'kills', 3),
  ('00000000-0000-0000-0000-00000d1bc001', date_trunc('hour', now()), 'x', 'xp', 9999);
insert into public.account_profile_daily (account_id, day, level, xp, gold, gems, diamonds, pokemon_count, dex_caught)
values ('00000000-0000-0000-0000-00000d1ac001', (now() at time zone 'America/Sao_Paulo')::date, 312, 5e6, 1e6, 40, 2, 90, 61);

-- arquivamento: o dia de 120 dias vira uma linha por métrica e sai de metric_hourly; o resto fica
do $$
declare
  v integer;
begin
  v := public.archive_metric_hourly();
  assert v = 2, format('apagou %s horas, esperava 2', v);
  assert (select value from public.metric_day where account_id = '00000000-0000-0000-0000-00000d1ac001'
           and metric = 'kills') = 80, 'arquivo não somou as hunts do dia';
  assert (select count(*) from public.metric_hourly where account_id = '00000000-0000-0000-0000-00000d1ac001') = 6,
    'apagou hora recente';
  v := public.archive_metric_hourly(); -- de novo: nada muda
  assert (select count(*) from public.metric_day where account_id = '00000000-0000-0000-0000-00000d1ac001') = 1,
    'arquivo duplicou';
end;
$$;

set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000d1a01', false);
do $$
declare
  r record;
  today date := (now() at time zone 'America/Sao_Paulo')::date;
begin
  assert (select count(*) from public.account_history(7)) = 7, 'esperava 7 dias de uma conta (a outra é de outro dono)';
  select * into r from public.account_history(7) where day = today;
  assert r.xp = 1500, format('xp de hoje %s ≠ 1500 (soma das hunts)', r.xp);
  assert r.active_minutes = 30 and r.disconnects = 2, 'minutos ou desconexões errados';
  assert r.level = 312 and r.gems = 40 and r.dex_caught = 61, 'perfil do dia não veio';
  -- "3 dias atrás" pode cair no dia anterior pelo fuso; a soma da semana é que vale
  assert (select sum(kills) from public.account_history(7)) = 40, 'abates da semana';
  assert (select count(*) from public.account_history(7) where level is null) = 6, 'dia sem perfil deve vir nulo';
  -- 130 dias: o dia arquivado vem de metric_day
  assert (select sum(kills) from public.account_history(130)) = 120, 'arquivo não entrou no histórico longo';
  assert (select count(*) from public.account_history(130)) = 130, 'grade de 130 dias';
  -- hunt_summary agora traz o XP
  assert (select xp from public.hunt_summary(now() - interval '1 day') where hunt_slug = 'x') = 1000, 'xp da hunt';
end;
$$;
reset role;

delete from public.metric_day where account_id in
  ('00000000-0000-0000-0000-00000d1ac001', '00000000-0000-0000-0000-00000d1bc001');
delete from public.metric_hourly where account_id in
  ('00000000-0000-0000-0000-00000d1ac001', '00000000-0000-0000-0000-00000d1bc001');
delete from public.account_profile_daily where account_id = '00000000-0000-0000-0000-00000d1ac001';
delete from public.accounts where nick in ('hi-a', 'hi-b');
delete from auth.users where id in ('00000000-0000-0000-0000-0000000d1a01', '00000000-0000-0000-0000-0000000d1b02');
do $$ begin raise notice 'historico: ok'; end $$;
