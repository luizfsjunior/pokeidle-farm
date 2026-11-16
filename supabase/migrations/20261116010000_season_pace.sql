-- Dia sazonal fora do ritmo medido (docs/design/simulador-4-decisoes.md).
--
-- Todo dia um tipo é sazonal: quem é desse tipo bate ×2 e apanha ÷4, selvagens incluídos. Os abates
-- passam a carimbar `season` (o tipo do dia); o metric_hourly guarda à parte os números dos abates
-- afetados (o tipo do dia é um dos tipos do ativo ou da espécie da hunt) e o rank_hunt_stats os
-- desconta, para o ritmo medido ser o de dias normais (no dia sazonal o worker o corrige pelo simulador).
-- As métricas totais (kills, xp...) não mudam. Abates antigos não têm `season`: nada a recalcular.

insert into public.metric_definitions (key, label, unit, kind, description, sort) values
  ('kills_season', 'Abates afetados pelo dia sazonal', 'abates', 'base',
   'Auxiliar: abates em que o tipo do dia é do ativo ou da hunt; fora do ritmo medido.', 992),
  ('active_minutes_season', 'Minutos ativos afetados pelo dia sazonal', 'min', 'base',
   'Auxiliar: minutos com abate afetado pelo dia sazonal.', 993),
  ('xp_season', 'XP dos abates afetados pelo dia sazonal', 'xp', 'base',
   'Auxiliar: XP dos abates afetados pelo dia sazonal.', 994),
  ('active_level_sum_season', 'Soma do nível do ativo (dia sazonal)', 'níveis', 'base',
   'Auxiliar: soma do nível do ativo nos abates afetados pelo dia sazonal.', 995),
  ('kills_leveled_season', 'Abates com nível do ativo (dia sazonal)', 'abates', 'base',
   'Auxiliar: abates afetados pelo dia sazonal com nível do ativo conhecido.', 996);

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
  with dv as (
    -- fase 7: cada drop (com qty) vale a média do Mercado do último snapshot antes do fim da
    -- hora; sem média em ouro, o npc_price; fora do catálogo, nada (conta em drops_unpriced)
    select e.account_id,
           date_trunc('hour', e.received_at)  as hour,
           coalesce(e.data->>'hunt_slug', '') as hunt_slug,
           sum(q.qty)                                              as units,
           -- gemas: o menor entre a média de 7 dias e o menor anúncio aberto (o preço de venda real)
           sum(q.qty * coalesce(least(po.avg, ask.min_price), po.avg, 0)) as value_orb,
           sum(q.qty * coalesce(pg.avg, gi.npc_price, 0))          as value_gold,
           coalesce(sum(q.qty) filter (where gi.item_id is null), 0) as unpriced
      from public.events e
      cross join lateral jsonb_array_elements(
             case when jsonb_typeof(e.data->'drops') = 'array' then e.data->'drops' else '[]'::jsonb end) d
      cross join lateral (
             select coalesce(nullif(d->>'qty', '')::numeric, 1) as qty, d->>'name' as name) q
      left join lateral (
             select i.item_id, i.npc_price from public.game_items i
              where i.name = q.name order by i.item_id limit 1) gi on true
      left join lateral (
             select max(m.taken_at) as taken_at from public.market_prices m
              where m.taken_at < date_trunc('hour', e.received_at) + interval '1 hour') s on true
      left join lateral (
             select m.avg from public.market_prices m
              where m.taken_at = s.taken_at and m.item_id = gi.item_id and m.currency = 'orb') po on true
      left join lateral (
             select m.avg from public.market_prices m
              where m.taken_at = s.taken_at and m.item_id = gi.item_id and m.currency = 'gold') pg on true
      left join lateral (
             select k.min_price from public.market_asks k
              where k.item_id = gi.item_id and k.currency = 'orb'
                and k.taken_at < date_trunc('hour', e.received_at) + interval '1 hour'
                and k.taken_at >= date_trunc('hour', e.received_at) - interval '6 hours'
              order by k.taken_at desc limit 1) ask on true
     where e.type = 'kill' and e.received_at >= v_from and e.received_at < v_to
     group by 1, 2, 3
  )
  select a.account_id, a.hour, a.hunt_slug, v.metric, v.value
    from (
      select e.account_id,
             date_trunc('hour', e.received_at)          as hour,
             coalesce(e.data->>'hunt_slug', '')         as hunt_slug,
             count(*) filter (where e.type = 'kill')    as kills,
             sum((e.data->>'xp')::numeric) filter (where e.type = 'kill') as xp,
             sum(coalesce((e.data->>'gold')::numeric, 0)
               + coalesce((e.data->>'gold_autosell')::numeric, 0)) filter (where e.type = 'kill') as gold,
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
                                and coalesce((e.data->>'scores')::boolean, false)) as rank_points,
             -- nível do pokémon ativo nos abates (docs/design/ritmo-por-nivel.md)
             sum((e.data->>'active_level')::numeric)
               filter (where e.type = 'kill' and jsonb_typeof(e.data->'active_level') = 'number') as active_level_sum,
             count(*) filter (where e.type = 'kill' and jsonb_typeof(e.data->'active_level') = 'number') as kills_leveled,
             -- os mesmos números só dos abates afetados pelo dia sazonal (o rank_hunt_stats desconta)
             count(*) filter (where s.season_hit) as kills_season,
             count(distinct date_trunc('minute', e.received_at)) filter (where s.season_hit) as active_minutes_season,
             sum((e.data->>'xp')::numeric) filter (where s.season_hit) as xp_season,
             sum((e.data->>'active_level')::numeric)
               filter (where s.season_hit and jsonb_typeof(e.data->'active_level') = 'number') as active_level_sum_season,
             count(*) filter (where s.season_hit and jsonb_typeof(e.data->'active_level') = 'number') as kills_leveled_season
        from public.events e
        -- dia sazonal (docs/design/simulador-4-decisoes.md): o abate é "afetado" se o tipo do dia
        -- é um dos tipos do pokémon ativo ou da espécie da hunt; fica fora do ritmo medido
        left join public.game_hunts gh on gh.slug = e.data->>'hunt_slug'
        left join public.game_species sh on sh.species_id = gh.species_id
        left join public.game_species sa
               on jsonb_typeof(e.data->'active_species_id') = 'number'
              and sa.species_id = (e.data->>'active_species_id')::bigint
        cross join lateral (
          select e.type = 'kill'
             and coalesce(e.data->>'season', '') <> ''
             and upper(e.data->>'season') in (upper(coalesce(sh.type1, '')), upper(coalesce(sh.type2, '')),
                                              upper(coalesce(sa.type1, '')), upper(coalesce(sa.type2, '')))
             as season_hit
        ) s
       where e.received_at >= v_from and e.received_at < v_to
       group by 1, 2, 3
    ) a
    left join dv on dv.account_id = a.account_id and dv.hour = a.hour and dv.hunt_slug = a.hunt_slug
    cross join lateral (values
      ('kills', a.kills::numeric), ('xp', a.xp), ('gold', a.gold), ('drops', dv.units),
      ('capture_attempts', a.capture_attempts), ('captures', a.captures), ('shinies', a.shinies),
      ('pokecenter', a.pokecenter), ('disconnects', a.disconnects), ('active_minutes', a.active_minutes),
      ('consumables_gold', a.consumables_gold),
      ('gold_net', coalesce(a.gold, 0) - a.consumables_gold),
      ('rank_points', a.rank_points),
      ('drops_value_orb', dv.value_orb), ('drops_value_gold', dv.value_gold),
      ('drops_unpriced', dv.unpriced),
      ('active_level_sum', a.active_level_sum), ('kills_leveled', a.kills_leveled::numeric),
      ('kills_season', a.kills_season::numeric), ('active_minutes_season', a.active_minutes_season::numeric),
      ('xp_season', a.xp_season), ('active_level_sum_season', a.active_level_sum_season),
      ('kills_leveled_season', a.kills_leveled_season::numeric)
    ) v (metric, value)
   where v.value is not null and v.value <> 0;

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

revoke all on function public.refresh_metric_hourly(timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.refresh_metric_hourly(timestamptz, timestamptz) to service_role;

drop function public.rank_hunt_stats(uuid, timestamptz);

create function public.rank_hunt_stats(p_account uuid, p_since timestamptz)
returns table (
  hunt_slug      text,
  kills          numeric,
  active_minutes numeric,
  last_chance    double precision,
  last_ball_id   int,
  avg_active_level numeric,  -- nível médio do pokémon ativo nos abates medidos (nulo se não houver)
  xp             numeric     -- XP do treinador nos abates (com os bônus)
)
language sql
stable
security definer
set search_path = ''
as $$
  with m as (
    select h.hunt_slug,
           -- sem os abates afetados pelo dia sazonal (métricas *_season): o ritmo é de dias normais
           coalesce(sum(h.value) filter (where h.metric = 'kills'), 0)
             - coalesce(sum(h.value) filter (where h.metric = 'kills_season'), 0) as kills,
           coalesce(sum(h.value) filter (where h.metric = 'active_minutes'), 0)
             - coalesce(sum(h.value) filter (where h.metric = 'active_minutes_season'), 0) as active_minutes,
           (coalesce(sum(h.value) filter (where h.metric = 'active_level_sum'), 0)
             - coalesce(sum(h.value) filter (where h.metric = 'active_level_sum_season'), 0))
             / nullif(coalesce(sum(h.value) filter (where h.metric = 'kills_leveled'), 0)
                      - coalesce(sum(h.value) filter (where h.metric = 'kills_leveled_season'), 0), 0)
             as avg_active_level,
           coalesce(sum(h.value) filter (where h.metric = 'xp'), 0)
             - coalesce(sum(h.value) filter (where h.metric = 'xp_season'), 0) as xp
      from public.metric_hourly h
     where h.account_id = p_account
       and h.hunt_slug <> ''
       and h.hour >= date_trunc('hour', p_since)
       and h.metric in ('kills', 'active_minutes', 'active_level_sum', 'kills_leveled', 'xp',
                        'kills_season', 'active_minutes_season', 'active_level_sum_season',
                        'kills_leveled_season', 'xp_season')
     group by h.hunt_slug
  ),
  c as (
    select distinct on (e.data->>'hunt_slug')
           e.data->>'hunt_slug'                    as hunt_slug,
           (e.data->>'chance')::double precision    as last_chance,
           case when jsonb_typeof(e.data->'ball_id') = 'number'
                then (e.data->>'ball_id')::int end  as last_ball_id
      from public.events e
     where e.account_id = p_account
       and e.type = 'capture_attempt'
       and e.received_at >= p_since
       and jsonb_typeof(e.data->'chance') = 'number'
       and coalesce(e.data->>'hunt_slug', '') <> ''
     order by e.data->>'hunt_slug', e.received_at desc
  )
  select coalesce(m.hunt_slug, c.hunt_slug),
         coalesce(m.kills, 0),
         coalesce(m.active_minutes, 0),
         c.last_chance,
         c.last_ball_id,
         m.avg_active_level,
         coalesce(m.xp, 0)
    from m
    full join c on c.hunt_slug = m.hunt_slug;
$$;

revoke all on function public.rank_hunt_stats(uuid, timestamptz) from public, anon, authenticated;
grant execute on function public.rank_hunt_stats(uuid, timestamptz) to service_role;
