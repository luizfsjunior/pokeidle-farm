-- Fase 3b, passo 6: métrica rank_points (docs/design/fase-3b-metricas-e-card.md, seção 1).
-- Espécies novas na semana do Top Catch: rank.catch com scores = true, por hora e hunt.
-- Somada numa semana, dá as espécies que pontuaram com o worker conectado.

insert into public.metric_definitions (key, label, unit, kind, description, sort) values
  ('rank_points', 'Espécies novas na semana', 'espécies', 'base',
   'Espécies que pontuaram no Top Catch (rank.catch com scores).', 75);

insert into public.metric_definitions (key, label, unit, kind, numerator, denominator, scale, description, sort) values
  ('rank_points_per_hour', 'Espécies novas por hora ativa', 'espécies/h', 'ratio',
   'rank_points', 'active_minutes', 60, '', 145);

create or replace function public.refresh_metric_hourly(p_from timestamptz, p_to timestamptz)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_from timestamptz := date_trunc('hour', p_from);
  v_to   timestamptz := date_trunc('hour', p_to) + interval '1 hour';
  v_rows int;
begin
  perform pg_advisory_xact_lock(hashtext('public.refresh_metric_hourly'));

  delete from public.metric_hourly where hour >= v_from and hour < v_to;

  insert into public.metric_hourly (account_id, hour, hunt_slug, metric, value)
  select a.account_id, a.hour, a.hunt_slug, v.metric, v.value
    from (
      select e.account_id,
             date_trunc('hour', e.received_at)          as hour,
             coalesce(e.data->>'hunt_slug', '')         as hunt_slug,
             count(*) filter (where e.type = 'kill')    as kills,
             sum((e.data->>'xp')::numeric) filter (where e.type = 'kill') as xp,
             sum(coalesce((e.data->>'gold')::numeric, 0)
               + coalesce((e.data->>'gold_autosell')::numeric, 0)) filter (where e.type = 'kill') as gold,
             sum(jsonb_array_length(coalesce(e.data->'drops', '[]'::jsonb))) filter (where e.type = 'kill') as drops,
             count(*) filter (where e.type = 'capture_attempt')  as capture_attempts,
             count(*) filter (where e.type = 'pokemon.captured') as captures,
             count(*) filter (where e.type = 'pokemon.captured'
                                and coalesce((e.data->>'shiny')::boolean, false)) as shinies,
             count(*) filter (where e.type = 'pokecenter')           as pokecenter,
             count(*) filter (where e.type = 'session.disconnected') as disconnects,
             count(distinct date_trunc('minute', e.received_at)) filter (where e.type = 'kill') as active_minutes,
             -- custo dos consumíveis: bolas lançadas + poções e revives gastos
             coalesce(sum((e.data->>'ball_price')::numeric) filter (where e.type = 'capture_attempt'), 0)
               + coalesce(sum((e.data->>'qty')::numeric * (e.data->>'unit_price')::numeric)
                            filter (where e.type = 'item.consumed'), 0) as consumables_gold,
             -- fase 3b: espécie nova na semana do Top Catch
             count(*) filter (where e.type = 'rank.catch'
                                and coalesce((e.data->>'scores')::boolean, false)) as rank_points
        from public.events e
       where e.received_at >= v_from and e.received_at < v_to
       group by 1, 2, 3
    ) a
    cross join lateral (values
      ('kills', a.kills::numeric), ('xp', a.xp), ('gold', a.gold), ('drops', a.drops),
      ('capture_attempts', a.capture_attempts), ('captures', a.captures), ('shinies', a.shinies),
      ('pokecenter', a.pokecenter), ('disconnects', a.disconnects), ('active_minutes', a.active_minutes),
      ('consumables_gold', a.consumables_gold),
      ('gold_net', coalesce(a.gold, 0) - a.consumables_gold),
      ('rank_points', a.rank_points)
    ) v (metric, value)
   where v.value is not null and v.value <> 0;

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

revoke all on function public.refresh_metric_hourly(timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.refresh_metric_hourly(timestamptz, timestamptz) to service_role;

-- o rank.catch é gravado desde 14/11/2026
select public.refresh_metric_hourly('2026-11-14 00:00+00', now());
