-- Testes da migration de métricas. Precisa de eventos em public.events
-- (ex.: gerados pelo simulador) e de uma conta com dono. Falha com exceção.
\set ON_ERROR_STOP 1

do $$
declare
  v_owner uuid;
  v_acc   uuid;
  v_n     numeric;
  v_m     numeric;
  v_goal  uuid;
  p       record;
begin
  select a.owner_id, a.id into v_owner, v_acc from public.accounts a limit 1;

  -- 1. backfill completo bate com a contagem direta
  perform public.refresh_metric_hourly('2000-01-01', now());
  select count(*) into v_n from public.events where type = 'kill';
  select sum(value) into v_m from public.metric_hourly where metric = 'kills';
  assert v_n = v_m, format('kills: eventos %s ≠ agregado %s', v_n, v_m);

  select sum((data->>'xp')::numeric) into v_n from public.events where type = 'kill';
  select sum(value) into v_m from public.metric_hourly where metric = 'xp';
  assert v_n = v_m, format('xp: %s ≠ %s', v_n, v_m);

  select count(*) into v_n from public.events where type = 'pokemon.captured';
  select sum(value) into v_m from public.metric_hourly where metric = 'captures';
  assert v_n = v_m, format('captures: %s ≠ %s', v_n, v_m);

  -- abates carimbados com hunt: nenhum abate em hunt ''
  assert not exists (select 1 from public.metric_hourly where metric = 'kills' and hunt_slug = ''),
    'abate sem hunt_slug';

  -- 2. idempotente
  perform public.refresh_metric_hourly('2000-01-01', now());
  select sum(value) into v_m from public.metric_hourly where metric = 'kills';
  select count(*) into v_n from public.events where type = 'kill';
  assert v_n = v_m, 'refresh não é idempotente';

  -- 3. incremental: apaga os agregados, roda e confere que recompõe tudo
  delete from public.metric_hourly;
  perform public.refresh_metrics_incremental();
  select sum(value) into v_m from public.metric_hourly where metric = 'kills';
  assert v_n = v_m, format('incremental: %s ≠ %s', v_n, v_m);
  -- segunda rodada (reprocessa a folga de 10 min) não muda o total
  perform public.refresh_metrics_incremental();
  select sum(value) into v_m from public.metric_hourly where metric = 'kills';
  assert v_n = v_m, format('incremental repetido: %s ≠ %s', v_n, v_m);

  -- 4. série: razão calculada com somas, dia no fuso de Brasília
  select sum(value) into v_m
    from public.metric_series('kills', now() - interval '4 days', now() + interval '1 hour', 'day');
  assert v_m = v_n, 'série diária de kills não soma o total';
  select avg(value) into v_m
    from public.metric_series('kills_per_hour', now() - interval '4 days', now(), 'hour');
  assert v_m between 300 and 420, format('kills_per_hour fora do esperado: %s', v_m);
  raise notice 'kills/h ativa (média das horas): %', round(v_m, 1);

  select avg(value) into v_m
    from public.metric_series('capture_rate', now() - interval '4 days', now(), 'day');
  assert v_m between 30 and 40, format('capture_rate fora do esperado: %s', v_m);
  raise notice 'taxa de captura: % %%', round(v_m, 1);

  -- 5. objetivo de métrica
  insert into public.goals (owner_id, name, kind, metric, target, starts_at, deadline)
  values (v_owner, 'Cem milhões de gold', 'metric', 'gold', 100000000,
          now() - interval '3 days', now() + interval '30 days')
  returning id into v_goal;
  select * into p from public.goal_progress(v_goal);
  raise notice 'gold: atual % | %/h | eta % | no prazo %', p.current, round(p.rate_per_hour), p.eta, p.on_track;
  assert p.current > 0 and p.rate_per_hour > 0 and p.eta is not null, 'objetivo de gold sem progresso';

  -- 6. objetivo de captura (Dratini bom) com chance até o prazo
  insert into public.goals (owner_id, name, kind, filter, target, starts_at, deadline)
  values (v_owner, 'Dratini bom', 'capture',
          '{"species": ["dratini"], "min_quality": 1.5, "min_ivs": {"atk": 28, "spe": 28}}',
          1, now() - interval '3 days', now() + interval '14 days')
  returning id into v_goal;
  select * into p from public.goal_progress(v_goal);
  raise notice 'dratini: atual % | p_match % | %/h | eta % | chance 14 dias %',
    p.current, round(p.p_match, 6), p.rate_per_hour, p.eta, p.chance_by_deadline;
  assert p.p_match > 0 and p.p_match < 0.01, format('p_match improvável: %s', p.p_match);
  assert p.chance_by_deadline between 0 and 1, 'chance fora de [0,1]';

  -- shiny usa a taxa dos Termos
  insert into public.goals (owner_id, name, kind, filter, target)
  values (v_owner, 'Shiny qualquer', 'capture', '{"shiny": true}', 1)
  returning id into v_goal;
  select * into p from public.goal_progress(v_goal);
  assert p.p_match = 1.0 / 24000, format('shiny p_match %s', p.p_match);

  -- objetivo de métrica com razão é recusado
  insert into public.goals (owner_id, name, kind, metric, target)
  values (v_owner, 'inválido', 'metric', 'kills_per_hour', 1) returning id into v_goal;
  begin
    perform public.goal_progress(v_goal);
    raise exception 'objetivo com razão deveria falhar';
  exception when raise_exception then
    if sqlerrm like '%deveria falhar%' then raise; end if;
  end;
  delete from public.goals where id = v_goal;

  -- 7. snapshots
  assert public.snapshot_goals() = 3, 'snapshot deveria gravar 3 objetivos';
  assert (select count(*) from public.goal_snapshots) = 3, 'snapshots não gravados';

  -- 8. poisson
  assert abs(public.poisson_at_least(1, 1) - (1 - exp(-1)::numeric)) < 1e-9, 'poisson k=1';
  assert public.poisson_at_least(0, 0) = 1 and public.poisson_at_least(3, 0) = 0, 'poisson bordas';

  raise notice 'OK: métricas';
end;
$$;

-- 9. RLS: outro usuário não vê nada; o dono vê o seu
do $$
declare
  v_owner uuid := (select owner_id from public.accounts limit 1);
  v_other uuid;
begin
  insert into auth.users default values returning id into v_other;

  perform set_config('request.jwt.claim.sub', v_other::text, true);
  set local role authenticated;
  assert (select count(*) from public.metric_hourly) = 0, 'RLS: outro usuário vê metric_hourly';
  assert (select count(*) from public.metric_daily) = 0,  'RLS: outro usuário vê metric_daily';
  assert (select count(*) from public.goals) = 0,         'RLS: outro usuário vê goals';
  assert (select count(*) from public.goal_snapshots) = 0,'RLS: outro usuário vê snapshots';
  assert (select count(*) from public.metric_definitions) > 0, 'definições deveriam ser públicas';
  reset role;

  perform set_config('request.jwt.claim.sub', v_owner::text, true);
  set local role authenticated;
  assert (select count(*) from public.metric_hourly) > 0, 'RLS: dono não vê metric_hourly';
  assert (select count(*) from public.goals) = 3, 'RLS: dono não vê goals';
  assert (select current from public.goal_progress((select id from public.goals where name = 'Cem milhões de gold'))) > 0,
    'goal_progress pelo painel não enxerga dados';
  reset role;

  raise notice 'OK: RLS';
end;
$$;
