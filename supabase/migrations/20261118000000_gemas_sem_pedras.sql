-- Pedras não são fonte de gemas (docs/design/painel-ux-v2.md, seção 1).
--
-- As pedras (game_items.category = 'stone': de evolução, Shiny Stones e Rough Gemstone) vendem a 2 gemas com
-- milhares na fila, mas a métrica drops_value_orb as valia pela média de 7 dias (12 a 78 gemas): a Compensa
-- chegou a dizer US$ 144/mês com 0 vendas. Agora:
-- - drops_value_orb não conta as pedras (o resto da regra é a mesma: o menor entre a média e o menor anúncio);
-- - evaluation_summary soma só as contas de farm (a pessoal entrava na renda);
-- - as horas novas já saem sem pedras; as antigas são recalculadas fora daqui (ver o fim do arquivo);
-- - índice parcial dos abates com drop: a página Economia lia 60 mil abates para achar ~400 com drop
--   (21 s, estourava o tempo do banco).

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
           -- gemas: o menor entre a média de 7 dias e o menor anúncio aberto (o preço de venda real);
           -- as pedras ficam de fora: não são fonte de gemas (docs/design/painel-ux-v2.md)
           sum(q.qty * coalesce(least(po.avg, ask.min_price), po.avg, 0))
             filter (where gi.category is distinct from 'stone') as value_orb,
           sum(q.qty * coalesce(pg.avg, gi.npc_price, 0))          as value_gold,
           coalesce(sum(q.qty) filter (where gi.item_id is null), 0) as unpriced
      from public.events e
      cross join lateral jsonb_array_elements(
             case when jsonb_typeof(e.data->'drops') = 'array' then e.data->'drops' else '[]'::jsonb end) d
      cross join lateral (
             select coalesce(nullif(d->>'qty', '')::numeric, 1) as qty, d->>'name' as name) q
      left join lateral (
             select i.item_id, i.npc_price, i.category from public.game_items i
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

-- Compensa: só as contas de farm (a mesma função de 20261116070000, com o filtro de role)
create or replace function public.evaluation_summary(p_days int default 7)
returns table (
  kind text, account_id uuid, nick text, gems numeric, gold numeric, active_hours numeric, data_days numeric,
  gems_per_day numeric, gems_per_hour numeric, month_gems_as_is numeric, month_gems_24h numeric,
  income_usd_as_is numeric, income_usd_24h numeric, cost_usd numeric, profit_usd_as_is numeric, profit_usd_24h numeric
)
language plpgsql
stable
set search_path = ''
as $$
declare
  v_now    timestamptz := date_trunc('hour', now()) + interval '1 hour';
  v_start  timestamptz := date_trunc('hour', now()) - make_interval(days => p_days);
  v_fee    numeric;
  v_usd    numeric;
  v_cost   numeric;
  v_energy numeric;
  s        public.evaluation_settings;
begin
  select c.orb_fee, c.usd_per_orb into v_fee, v_usd from public.evaluation_constants() c;

  -- só conta a partir do primeiro snapshot de preços: antes dele os drops não têm valor em
  -- gemas e só diluiriam a média (análise de 15/11, proposta D)
  v_start := greatest(v_start, coalesce(
    (select date_trunc('hour', min(m.taken_at)) from public.market_prices m), v_start));

  select * into s from public.evaluation_settings where owner_id = (select auth.uid());
  if found and s.marginal then
    v_energy := 0;
  elsif found and s.machine_watts is not null and s.kwh_price_brl is not null and s.usd_brl is not null then
    v_energy := s.machine_watts / 1000 * 24 * 30 * s.kwh_price_brl / s.usd_brl;
  end if;
  -- custo do mês = energia + fixo (VPS e proxy); desconhecido só se os dois forem
  if v_energy is not null or s.fixed_cost_usd is not null then
    v_cost := coalesce(v_energy, 0) + coalesce(s.fixed_cost_usd, 0);
  end if;

  return query
  with per_account as (
    select a.id as account_id, a.nick,
           coalesce(sum(m.value) filter (where m.metric = 'drops_value_orb'), 0)  as gems,
           coalesce(sum(m.value) filter (where m.metric = 'drops_value_gold'), 0) as gold,
           coalesce(sum(m.value) filter (where m.metric = 'active_minutes'), 0) / 60 as active_hours,
           least(p_days::numeric,
                 extract(epoch from v_now - min(m.hour) filter (where m.metric = 'kills')) / 86400) as data_days
      from public.accounts a
      join public.metric_hourly m on m.account_id = a.id and m.hour >= v_start
     where a.role = 'farm'
     group by a.id, a.nick
  ),
  acc as (
    select p.*,
           case when p.data_days > 0 then p.gems / p.data_days end           as per_day,
           case when p.active_hours > 0 then p.gems / p.active_hours end      as per_hour
      from per_account p
  ),
  rows as (
    select 'account'::text as kind, a.account_id, a.nick, a.gems, a.gold, a.active_hours, a.data_days,
           a.per_day, a.per_hour, a.per_day * 30 as month_as_is, a.per_hour * 24 * 30 as month_24h,
           null::numeric as cost
      from acc a
    union all
    select 'total', null, null, sum(a.gems), sum(a.gold), sum(a.active_hours), max(a.data_days),
           sum(a.per_day),
           case when sum(a.active_hours) > 0 then sum(a.gems) / sum(a.active_hours) end,
           sum(a.per_day) * 30, sum(a.per_hour * 24 * 30), v_cost
      from acc a
    having count(*) > 0
    union all
    select 'three_accounts', null, null, null, null, null, null,
           avg(a.per_day) * 3, null, avg(a.per_day) * 30 * 3, avg(a.per_hour * 24 * 30) * 3, v_cost
      from acc a
    having count(*) > 0
  )
  select r.kind, r.account_id, r.nick, r.gems, r.gold, r.active_hours, r.data_days,
         r.per_day, r.per_hour, r.month_as_is, r.month_24h,
         r.month_as_is * (1 - v_fee) * v_usd,
         r.month_24h * (1 - v_fee) * v_usd,
         r.cost,
         r.month_as_is * (1 - v_fee) * v_usd - coalesce(r.cost, 0),
         r.month_24h * (1 - v_fee) * v_usd - coalesce(r.cost, 0)
    from rows r
   order by case r.kind when 'account' then 0 when 'total' then 1 else 2 end, r.nick;
end;
$$;

-- só os abates com drop (~0,7% deles); casa com o filtro do painel (economia/market.ts)
create index if not exists events_kill_drops on public.events (received_at)
  where type = 'kill' and (data -> 'drops') <> '[]'::jsonb;

-- Sem recálculo aqui: 1 dia de métricas leva ~50 s e a migration roda numa transação só (a integração do GitHub),
-- segurando a trava do refresh. Os dias anteriores são recalculados depois, um por chamada
-- (select public.refresh_metric_hourly(<dia>, <dia> + interval '1 day' - interval '1 hour')).
