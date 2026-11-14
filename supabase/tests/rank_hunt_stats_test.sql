-- Teste da função rank_hunt_stats (fase 3b, plugin rank). Cria os próprios dados (em 2001) e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values ('00000000-0000-0000-0000-0000000000c1');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-000000000c01', '00000000-0000-0000-0000-0000000000c1', 'rank-1', 'farm'),
  ('00000000-0000-0000-0000-000000000c02', '00000000-0000-0000-0000-0000000000c1', 'rank-2', 'farm');

insert into public.metric_hourly (account_id, hour, hunt_slug, metric, value) values
  ('00000000-0000-0000-0000-000000000c01', '2001-11-12 10:00Z', 'magikarp', 'kills', 300),
  ('00000000-0000-0000-0000-000000000c01', '2001-11-12 10:00Z', 'magikarp', 'active_minutes', 50),
  ('00000000-0000-0000-0000-000000000c01', '2001-11-12 11:00Z', 'magikarp', 'kills', 200),
  ('00000000-0000-0000-0000-000000000c01', '2001-11-12 11:00Z', 'magikarp', 'active_minutes', 30),
  ('00000000-0000-0000-0000-000000000c01', '2001-11-12 11:00Z', 'magikarp', 'gold', 9999),
  ('00000000-0000-0000-0000-000000000c01', '2001-11-12 11:00Z', '', 'kills', 7),
  ('00000000-0000-0000-0000-000000000c01', '2001-11-01 10:00Z', 'magikarp', 'kills', 1000),
  ('00000000-0000-0000-0000-000000000c02', '2001-11-12 10:00Z', 'magikarp', 'kills', 555);

insert into public.events (id, account_id, session_id, type, received_at, data)
select gen_random_uuid(), '00000000-0000-0000-0000-000000000c01', gen_random_uuid(), t, at::timestamptz, d::jsonb
  from (values
    ('capture_attempt', '2001-11-12 10:00Z', '{"hunt_slug":"magikarp","chance":0.01,"ball_id":1}'),
    ('capture_attempt', '2001-11-12 10:05Z', '{"hunt_slug":"magikarp","chance":0.04,"ball_id":4}'),
    ('capture_attempt', '2001-11-12 10:09Z', '{"hunt_slug":"magikarp","chance":null,"ball_id":4}'),
    ('capture_attempt', '2001-11-12 10:10Z', '{"hunt_slug":"magikarp","ball_id":4}'),
    ('capture_attempt', '2001-11-12 10:10Z', '{"hunt_slug":"caterpie","chance":0.02,"ball_id":2}'),
    ('capture_attempt', '2001-11-01 10:10Z', '{"hunt_slug":"metapod","chance":0.03,"ball_id":2}'),
    ('kill',            '2001-11-12 10:10Z', '{"hunt_slug":"magikarp","chance":0.5}')
  ) as v(t, at, d);

do $$
declare
  acc constant uuid := '00000000-0000-0000-0000-000000000c01';
  r record;
begin
  -- since às 10:30: os abates contam a partir da hora 10:00; as tentativas de antes ficam de fora
  assert (select count(*) from public.rank_hunt_stats(acc, '2001-11-12 10:30Z')) = 1, 'uma hunt depois das 10:30';
  select * into r from public.rank_hunt_stats(acc, '2001-11-12 10:30Z');
  assert r.hunt_slug = 'magikarp' and r.kills = 500 and r.active_minutes = 80, 'abates e minutos';
  assert r.last_chance is null, 'sem tentativa depois das 10:30';

  -- since às 09:00
  select * into r from public.rank_hunt_stats(acc, '2001-11-12 09:00Z') where hunt_slug = 'magikarp';
  assert r.last_chance = 0.04 and r.last_ball_id = 4, 'a chance mais recente (ignora sem chance)';
  select * into r from public.rank_hunt_stats(acc, '2001-11-12 09:00Z') where hunt_slug = 'caterpie';
  assert r.kills = 0 and r.active_minutes = 0 and r.last_chance = 0.02, 'hunt só com tentativa';
  assert not exists (
    select 1 from public.rank_hunt_stats(acc, '2001-11-12 09:00Z') where hunt_slug in ('', 'metapod')
  ), 'sem hunt vazia e respeita o since';

  assert not has_function_privilege('authenticated', 'public.rank_hunt_stats(uuid, timestamptz)', 'execute'),
    'authenticated não executa';
  assert has_function_privilege('service_role', 'public.rank_hunt_stats(uuid, timestamptz)', 'execute'),
    'service_role executa';

  delete from public.events where account_id = acc;
  delete from public.metric_hourly where account_id in (acc, '00000000-0000-0000-0000-000000000c02');
  delete from public.accounts where nick in ('rank-1', 'rank-2');
  delete from auth.users where id = '00000000-0000-0000-0000-0000000000c1';
  raise notice 'rank_hunt_stats: ok';
end;
$$;
