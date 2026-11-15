-- Preço real das pedras: menor anúncio aberto e a fila de cada item (docs/design/fase-9-venda-de-pedras.md).
--
-- Em 15/11 os 60 anúncios de Water Stone (4.607 unidades) estavam todos a 2 gemas, o mínimo do
-- Mercado, enquanto a "média de 7 dias" do market.medias dizia ~30. O valor dos drops em gemas
-- passa a usar o menor entre a média e o menor anúncio aberto (sem os anúncios da própria conta).

create table public.market_asks (
  taken_at      timestamptz not null,
  item_id       bigint not null,
  currency      text not null check (currency in ('orb', 'gold')),
  min_price     numeric,           -- nulo: nenhum anúncio aberto de outros vendedores
  units_at_min  numeric not null default 0,
  total_units   numeric not null default 0,
  listings      int not null default 0,
  primary key (taken_at, item_id, currency)
);
create index market_asks_item on public.market_asks (item_id, currency, taken_at desc);

alter table public.market_asks enable row level security;
create policy read_market_asks on public.market_asks for select to authenticated using (true);

create or replace function public.purge_market_prices()
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_rows int;
  v_asks int;
begin
  delete from public.market_prices where taken_at < now() - interval '30 days';
  get diagnostics v_rows = row_count;
  delete from public.market_asks where taken_at < now() - interval '30 days';
  get diagnostics v_asks = row_count;
  return v_rows + v_asks;
end;
$$;

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
                                and coalesce((e.data->>'scores')::boolean, false)) as rank_points
        from public.events e
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
      ('drops_unpriced', dv.unpriced)
    ) v (metric, value)
   where v.value is not null and v.value <> 0;

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

revoke all on function public.refresh_metric_hourly(timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.refresh_metric_hourly(timestamptz, timestamptz) to service_role;

select public.refresh_metric_hourly('2026-11-12 00:00+00', now());
