-- Teste das bolas por minuto e da retenção de 26/11 (docs/design/retencao-eventos.md, "26/11: bolas por minuto").
-- As mesmas bolas gravadas de dois jeitos têm de dar as mesmas métricas e a mesma última chance: a conta A
-- como eventos (worker antigo), a conta B somada em kill_minute (worker novo). A conta C testa o prune_events().
-- Cria os próprios dados e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values ('00000000-0000-0000-0000-0000000000f1');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-000000000f0a', '00000000-0000-0000-0000-0000000000f1', 'bolas-eventos', 'farm'),
  ('00000000-0000-0000-0000-000000000f0b', '00000000-0000-0000-0000-0000000000f1', 'bolas-minutos', 'farm'),
  ('00000000-0000-0000-0000-000000000f0c', '00000000-0000-0000-0000-0000000000f1', 'bolas-prune', 'farm');

-- conta A: um abate e três bolas como eventos (10:01 e 10:02 em rochaz, 10:05 em folhaz)
insert into public.events (id, account_id, session_id, type, received_at, data)
select gen_random_uuid(), '00000000-0000-0000-0000-000000000f0a', '00000000-0000-0000-0000-00000000006a',
       t, at::timestamptz, d::jsonb
  from (values
    ('kill', '2001-11-12 10:01:05Z', '{"hunt_slug":"rochaz","xp":100,"gold":40,"gold_autosell":0,"drops":[]}'),
    ('capture_attempt', '2001-11-12 10:01:10Z', '{"hunt_slug":"rochaz","ball_price":10,"chance":0.05,"ball_id":1,"success":false}'),
    ('capture_attempt', '2001-11-12 10:01:50Z', '{"hunt_slug":"rochaz","ball_price":10,"chance":0.06,"ball_id":2,"success":true}'),
    ('capture_attempt', '2001-11-12 10:02:30Z', '{"hunt_slug":"rochaz","ball_price":50,"chance":0.2,"ball_id":4,"success":false}'),
    ('capture_attempt', '2001-11-12 10:05:00Z', '{"hunt_slug":"folhaz","ball_price":10,"chance":null,"ball_id":1}'),
    ('pokemon.captured', '2001-11-12 10:01:51Z', '{"hunt_slug":"rochaz","shiny":false}')
  ) as v(t, at, d);

-- conta B: o mesmo, com o abate e as bolas somados por minuto (as bolas sem pokémon ativo nem dia sazonal)
insert into public.kill_minute (account_id, session_id, minute, hunt_slug, active_species_id, season, part,
                                kills, xp, gold, capture_attempts, capture_successes, balls_gold,
                                last_chance, last_ball_id)
values
  ('00000000-0000-0000-0000-000000000f0b', '00000000-0000-0000-0000-00000000006b', '2001-11-12 10:01Z',
   'rochaz', 7, '', 0, 1, 100, 40, 0, 0, 0, null, null),
  ('00000000-0000-0000-0000-000000000f0b', '00000000-0000-0000-0000-00000000006b', '2001-11-12 10:01Z',
   'rochaz', 0, '', 0, 0, 0, 0, 2, 1, 20, 0.06, 2),
  ('00000000-0000-0000-0000-000000000f0b', '00000000-0000-0000-0000-00000000006b', '2001-11-12 10:02Z',
   'rochaz', 0, '', 0, 0, 0, 0, 1, 0, 50, 0.2, 4),
  ('00000000-0000-0000-0000-000000000f0b', '00000000-0000-0000-0000-00000000006b', '2001-11-12 10:05Z',
   'folhaz', 0, '', 0, 0, 0, 0, 1, 0, 10, null, null);
insert into public.events (id, account_id, session_id, type, received_at, data) values
  (gen_random_uuid(), '00000000-0000-0000-0000-000000000f0b', '00000000-0000-0000-0000-00000000006b',
   'pokemon.captured', '2001-11-12 10:01:51Z', '{"hunt_slug":"rochaz","shiny":false}');

-- conta C: eventos de 3 dias atrás (o prune apaga o ruído de 2 dias e guarda o que a página de Vendas lê)
insert into public.events (id, account_id, session_id, type, received_at, data)
select gen_random_uuid(), '00000000-0000-0000-0000-000000000f0c', '00000000-0000-0000-0000-00000000006c',
       t, now() - interval '3 days', d::jsonb
  from (values
    ('action.sent', '{"action":"ball.throw"}'),
    ('action.sent', '{"action":"shop.buy"}'),
    ('action.blocked', '{"action":"shop.buy","reason":"rate_limit"}'),
    ('action.sent', '{"action":"market.criar"}'),
    ('action.sent', '{"action":"market.cancelar"}'),
    ('action.blocked', '{"action":"market.meus","reason":"rate_limit"}'),
    ('unknown', '{"t":"venda"}'),
    ('unknown', '{"t":"qualquer"}'),
    ('wild_fled', '{}'),
    ('pokemon.captured', '{}')
  ) as v(t, d);

do $$
declare
  a constant uuid := '00000000-0000-0000-0000-000000000f0a';
  b constant uuid := '00000000-0000-0000-0000-000000000f0b';
  c constant uuid := '00000000-0000-0000-0000-000000000f0c';
  v_diff int;
  v numeric;
  r record;
  v_left text;
begin
  perform public.refresh_metric_hourly('2001-11-12 10:00Z', '2001-11-12 10:00Z');

  select count(*) into v_diff from (
    (select hour, hunt_slug, metric, value from public.metric_hourly where account_id = a
     except select hour, hunt_slug, metric, value from public.metric_hourly where account_id = b)
    union all
    (select hour, hunt_slug, metric, value from public.metric_hourly where account_id = b
     except select hour, hunt_slug, metric, value from public.metric_hourly where account_id = a)
  ) x;
  assert v_diff = 0, format('%s métricas diferentes entre eventos e kill_minute', v_diff);

  select value into v from public.metric_hourly
   where account_id = b and hunt_slug = 'rochaz' and metric = 'capture_attempts';
  assert v = 3, format('capture_attempts %s ≠ 3', v);
  select value into v from public.metric_hourly
   where account_id = b and hunt_slug = 'rochaz' and metric = 'consumables_gold';
  assert v = 70, format('consumables_gold %s ≠ 70 (bolas de 10 + 10 + 50)', v);
  select value into v from public.metric_hourly
   where account_id = b and hunt_slug = 'rochaz' and metric = 'gold_net';
  assert v = -30, format('gold_net %s ≠ -30 (40 do abate − 70 de bolas)', v);
  select value into v from public.metric_hourly
   where account_id = b and hunt_slug = 'rochaz' and metric = 'active_minutes';
  assert v = 1, format('active_minutes %s ≠ 1 (minuto só de bola não é minuto ativo)', v);
  select value into v from public.metric_hourly
   where account_id = b and hunt_slug = 'folhaz' and metric = 'capture_attempts';
  assert v = 1, format('capture_attempts em folhaz %s ≠ 1', v);

  -- última chance por hunt: os dois jeitos dão o mesmo
  select count(*) into v_diff from (
    (select hunt_slug, last_chance, last_ball_id from public.rank_hunt_stats(a, '2001-11-12 00:00Z')
     except select hunt_slug, last_chance, last_ball_id from public.rank_hunt_stats(b, '2001-11-12 00:00Z'))
    union all
    (select hunt_slug, last_chance, last_ball_id from public.rank_hunt_stats(b, '2001-11-12 00:00Z')
     except select hunt_slug, last_chance, last_ball_id from public.rank_hunt_stats(a, '2001-11-12 00:00Z'))
  ) x;
  assert v_diff = 0, format('%s hunts com chance diferente em rank_hunt_stats', v_diff);
  select * into r from public.rank_hunt_stats(b, '2001-11-12 00:00Z') where hunt_slug = 'rochaz';
  assert r.last_chance = 0.2 and r.last_ball_id = 4, format('rochaz: chance %s bola %s', r.last_chance, r.last_ball_id);
  assert r.kills = 1, format('rochaz: kills %s ≠ 1', r.kills);
  select * into r from public.rank_hunt_stats(b, '2001-11-12 10:02Z') where hunt_slug = 'rochaz';
  assert r.last_chance = 0.2, 'a janela começa num minuto que tem bola';
  -- folhaz só teve bola sem chance: nada de chance
  assert not exists (select 1 from public.rank_hunt_stats(b, '2001-11-12 00:00Z') where hunt_slug = 'folhaz'),
    'folhaz sem chance nem abate não aparece';

  -- retenção
  perform public.prune_events();
  select string_agg(type || ':' || coalesce(data->>'action', data->>'t', ''), ',' order by type, data::text)
    into v_left from public.events where account_id = c;
  assert v_left = 'action.blocked:market.meus,action.sent:market.cancelar,action.sent:market.criar,'
                  'pokemon.captured:,unknown:venda',
    format('sobrou %s', v_left);

  delete from public.events where account_id in (a, b, c);
  delete from public.kill_minute where account_id in (a, b, c);
  delete from public.metric_hourly where account_id in (a, b, c);
  delete from public.accounts where id in (a, b, c);
  delete from auth.users where id = '00000000-0000-0000-0000-0000000000f1';
  raise notice 'bolas_por_minuto: ok';
end;
$$;
