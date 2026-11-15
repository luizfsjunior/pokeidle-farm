-- Teste da métrica rank_points (fase 3b, passo 6; docs/design/fase-3b-metricas-e-card.md,
-- casos 1 a 3). Cria a própria conta e eventos numa hora de 2001 e apaga tudo no fim.
\set ON_ERROR_STOP 1

do $$
declare
  v_owner uuid;
  v_acc   uuid;
  v_hour  timestamptz := '2001-01-01 10:00+00';
  v_pts   numeric;
  v_rate  numeric;
begin
  insert into auth.users default values returning id into v_owner;
  insert into public.accounts (owner_id, nick, role) values (v_owner, 'teste-rank-points', 'farm')
    returning id into v_acc;

  -- 30 minutos ativos na caterpie
  insert into public.events (id, account_id, session_id, type, received_at, data)
  select gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_hour + make_interval(mins => i),
         '{"gold": 10, "hunt_slug": "caterpie"}'
    from generate_series(0, 29) i;

  insert into public.events (id, account_id, session_id, type, received_at, data) values
    -- caso 1: dois que pontuam e um que não
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'rank.catch', v_hour + interval '5 min',
     '{"scores": true, "species_id": 10, "hunt_slug": "caterpie", "week_start": "2000-12-31"}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'rank.catch', v_hour + interval '6 min',
     '{"scores": true, "species_id": 11, "hunt_slug": "caterpie", "week_start": "2000-12-31"}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'rank.catch', v_hour + interval '7 min',
     '{"scores": false, "species_id": 10, "hunt_slug": "caterpie", "week_start": "2000-12-31"}'),
    -- caso 2: sem hunt_slug
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'rank.catch', v_hour + interval '8 min',
     '{"scores": true, "species_id": 13, "week_start": "2000-12-31"}');

  perform public.refresh_metric_hourly(v_hour, v_hour);

  select value into v_pts from public.metric_hourly
   where account_id = v_acc and metric = 'rank_points' and hunt_slug = 'caterpie';
  assert v_pts = 2, format('rank_points caterpie: %s ≠ 2', v_pts);
  select value into v_pts from public.metric_hourly
   where account_id = v_acc and metric = 'rank_points' and hunt_slug = '';
  assert v_pts = 1, format('rank_points sem hunt: %s ≠ 1', v_pts);

  -- caso 3: 2 pontos em 30 min ativos na caterpie → 4/h
  select value into v_rate
    from public.metric_series('rank_points_per_hour', v_hour, v_hour + interval '1 hour', 'hour',
                              v_acc, 'caterpie');
  assert v_rate = 4, format('rank_points_per_hour: %s ≠ 4', v_rate);

  delete from public.metric_hourly where account_id = v_acc;
  delete from public.accounts where id = v_acc;
  delete from auth.users where id = v_owner;
  raise notice 'rank_points: ok';
end;
$$;
