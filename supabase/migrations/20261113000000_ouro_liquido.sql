-- Ouro líquido (docs/design/fase-3-reposicao.md, seção 6).
--
-- consumables_gold: custo das bolas lançadas (capture_attempt.ball_price) mais
-- poções e revives gastos (item.consumed: qty × unit_price).
-- gold_net: gold − consumables_gold. Pode ser negativo.
--
-- Eventos antigos, sem ball_price, contam custo 0.

insert into public.metric_definitions (key, label, unit, kind, description, sort) values
  ('consumables_gold', 'Gasto com consumíveis', 'gold', 'base', 'Bolas lançadas, poções e revives gastos, a preço da loja.', 32),
  ('gold_net',         'Gold líquido',          'gold', 'base', 'Gold dos abates menos o gasto com consumíveis.', 34);

insert into public.metric_definitions (key, label, unit, kind, numerator, denominator, scale, description, sort) values
  ('gold_net_per_hour', 'Gold líquido por hora ativa', 'gold/h', 'ratio', 'gold_net', 'active_minutes', 60, '', 135);

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
                            filter (where e.type = 'item.consumed'), 0) as consumables_gold
        from public.events e
       where e.received_at >= v_from and e.received_at < v_to
       group by 1, 2, 3
    ) a
    cross join lateral (values
      ('kills', a.kills::numeric), ('xp', a.xp), ('gold', a.gold), ('drops', a.drops),
      ('capture_attempts', a.capture_attempts), ('captures', a.captures), ('shinies', a.shinies),
      ('pokecenter', a.pokecenter), ('disconnects', a.disconnects), ('active_minutes', a.active_minutes),
      ('consumables_gold', a.consumables_gold),
      ('gold_net', coalesce(a.gold, 0) - a.consumables_gold)
    ) v (metric, value)
   where v.value is not null and v.value <> 0;

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

revoke all on function public.refresh_metric_hourly(timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.refresh_metric_hourly(timestamptz, timestamptz) to service_role;
