-- Abates somados por minuto (docs/design/retencao-eventos.md, "Abates por minuto").
--
-- O worker gravava uma linha em events por abate: ~56 mil por dia com 4 contas, 140 MB em 4 dias. Mesmo com
-- 1 dia de retenção o banco ficava perto dos 500 MB do plano grátis. Agora a telemetria soma os abates e o
-- consumo de itens por minuto e grava uma linha em kill_minute (uns 6 mil por dia).
--
-- Chave: (conta, sessão, minuto, hunt, espécie do pokémon ativo, dia sazonal, parte). A espécie e o dia
-- sazonal entram porque o ritmo descontado do dia sazonal (season_hit) depende deles. `parte` cresce quando
-- chega um abate de um minuto que já foi gravado (fila atrasada): a linha nova não sobrescreve a anterior.
-- A gravação é `on conflict do nothing`, então reenviar o buffer local não conta duas vezes.
--
-- As leituras (refresh_metric_hourly, evaluation_liquidity, dropped_items) somam kill_minute com os abates que
-- ainda estão em events: o worker antigo continua gravando lá até ser atualizado, e o que ele gravou some no
-- prune_events em 1 dia.

create table public.kill_minute (
  account_id        uuid        not null references public.accounts (id) on delete cascade,
  session_id        uuid        not null,
  minute            timestamptz not null,
  hunt_slug         text        not null default '',
  active_species_id bigint      not null default 0,   -- 0: sem pokémon ativo conhecido
  season            text        not null default '',  -- tipo do dia sazonal ('' fora do dia)
  part              smallint    not null default 0,
  kills             int         not null default 0,
  xp                bigint      not null default 0,   -- XP do treinador
  gold              bigint      not null default 0,   -- ouro do abate + venda automática
  active_level_sum  bigint      not null default 0,   -- soma do nível do ativo nos abates com nível
  kills_leveled     int         not null default 0,   -- abates com o nível do ativo conhecido
  drops             jsonb       not null default '[]'::jsonb,  -- [{name, qty}], somado por nome
  consumables_gold  bigint      not null default 0,   -- poções e revives gastos (qty × preço)
  inserted_at       timestamptz not null default now(),
  primary key (account_id, session_id, minute, hunt_slug, active_species_id, season, part)
);
create index kill_minute_account_minute on public.kill_minute (account_id, minute desc);
create index kill_minute_minute on public.kill_minute (minute);
create index kill_minute_inserted on public.kill_minute (inserted_at);

alter table public.kill_minute enable row level security;
create policy own_kill_minute on public.kill_minute
  for select to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())));

-- ---------------------------------------------------------------------------
-- Drops por item desde `p_since` (kill_minute + abates antigos em events). Painel (Mercado) e liquidez.
-- security invoker: no painel, a RLS limita às contas do dono.
-- ---------------------------------------------------------------------------
create function public.dropped_items(p_since timestamptz, p_account uuid default null)
returns table (name text, qty numeric)
language sql
stable
set search_path = ''
as $$
  with src as (
    select k.drops
      from public.kill_minute k
     where k.minute >= date_trunc('minute', p_since)
       and (p_account is null or k.account_id = p_account)
    union all
    select e.data->'drops'
      from public.events e
     where e.type = 'kill' and e.received_at >= p_since
       and (p_account is null or e.account_id = p_account)
  )
  select d->>'name', sum(coalesce(nullif(d->>'qty', '')::numeric, 1))
    from src
    cross join lateral jsonb_array_elements(
           case when jsonb_typeof(src.drops) = 'array' then src.drops else '[]'::jsonb end) d
   where d->>'name' is not null
   group by 1;
$$;

revoke all on function public.dropped_items(timestamptz, uuid) from public, anon;
grant execute on function public.dropped_items(timestamptz, uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Liquidez dos drops: mesma conta de antes, com os drops de dropped_items.
-- ---------------------------------------------------------------------------
create or replace function public.evaluation_liquidity(p_days integer default 7)
returns table (name text, item_id bigint, dropped numeric, dropped_week numeric, sold_week numeric,
               share numeric, flagged boolean)
language sql
stable
set search_path = ''
as $$
  with drops as (
    select x.name, x.qty from public.dropped_items(now() - make_interval(days => p_days)) x
  ),
  snap as (select max(taken_at) as taken_at from public.market_prices)
  select d.name, gi.item_id, d.qty, d.qty * 7 / p_days,
         mp.units * 7 / nullif(coalesce(mp.days, 7), 0),
         (d.qty * 7 / p_days) / nullif(mp.units * 7 / nullif(coalesce(mp.days, 7), 0), 0),
         coalesce((d.qty * 7 / p_days) / nullif(mp.units * 7 / nullif(coalesce(mp.days, 7), 0), 0) > 0.10,
                  false)
    from drops d
    left join lateral (
           select i.item_id from public.game_items i where i.name = d.name order by i.item_id limit 1) gi on true
    left join lateral (
           select m.units, m.days from public.market_prices m, snap
            where m.taken_at = snap.taken_at and m.item_id = gi.item_id and m.currency = 'orb') mp on true
   order by 7 desc, 4 desc;
$$;

-- ---------------------------------------------------------------------------
-- Métricas por hora: os abates e o consumo vêm de kill_minute (e, na transição, de events); o resto continua
-- vindo de events. As métricas e os nomes são os mesmos de antes.
-- ---------------------------------------------------------------------------
create or replace function public.refresh_metric_hourly(p_from timestamptz, p_to timestamptz)
returns integer
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
  with km as (
    -- abates e consumo: uma linha por minuto (kill_minute) ou por evento (worker antigo, em events)
    select k.account_id, k.minute, k.hunt_slug, k.active_species_id, k.season,
           k.kills, k.xp::numeric as xp, k.gold::numeric as gold,
           k.active_level_sum::numeric as active_level_sum, k.kills_leveled,
           k.drops, k.consumables_gold::numeric as consumables_gold
      from public.kill_minute k
     where k.minute >= v_from and k.minute < v_to
    union all
    select e.account_id, date_trunc('minute', e.received_at), coalesce(e.data->>'hunt_slug', ''),
           case when jsonb_typeof(e.data->'active_species_id') = 'number'
                then (e.data->>'active_species_id')::bigint else 0 end,
           coalesce(e.data->>'season', ''),
           (e.type = 'kill')::int,
           case when e.type = 'kill' then coalesce((e.data->>'xp')::numeric, 0) else 0 end,
           case when e.type = 'kill' then coalesce((e.data->>'gold')::numeric, 0)
                                        + coalesce((e.data->>'gold_autosell')::numeric, 0) else 0 end,
           case when e.type = 'kill' and jsonb_typeof(e.data->'active_level') = 'number'
                then (e.data->>'active_level')::numeric else 0 end,
           (e.type = 'kill' and jsonb_typeof(e.data->'active_level') = 'number')::int,
           case when e.type = 'kill' and jsonb_typeof(e.data->'drops') = 'array'
                then e.data->'drops' else '[]'::jsonb end,
           case when e.type = 'item.consumed'
                then coalesce((e.data->>'qty')::numeric * (e.data->>'unit_price')::numeric, 0) else 0 end
      from public.events e
     where e.type in ('kill', 'item.consumed') and e.received_at >= v_from and e.received_at < v_to
  ),
  kmx as (
    -- dia sazonal (docs/design/simulador-4-decisoes.md): o abate é "afetado" se o tipo do dia
    -- é um dos tipos do pokémon ativo ou da espécie da hunt; fica fora do ritmo medido
    select km.*, date_trunc('hour', km.minute) as hour,
           (km.kills > 0
            and km.season <> ''
            and upper(km.season) in (upper(coalesce(sh.type1, '')), upper(coalesce(sh.type2, '')),
                                     upper(coalesce(sa.type1, '')), upper(coalesce(sa.type2, ''))))
             as season_hit
      from km
      left join public.game_hunts gh on gh.slug = km.hunt_slug
      left join public.game_species sh on sh.species_id = gh.species_id
      left join public.game_species sa on km.active_species_id > 0 and sa.species_id = km.active_species_id
  ),
  kagg as (
    select account_id, hour, hunt_slug,
           sum(kills)                                            as kills,
           sum(xp) filter (where kills > 0)                      as xp,
           sum(gold) filter (where kills > 0)                    as gold,
           count(distinct minute) filter (where kills > 0)       as active_minutes,
           sum(consumables_gold)                                 as items_gold,
           -- nível do pokémon ativo nos abates (docs/design/ritmo-por-nivel.md)
           sum(active_level_sum) filter (where kills_leveled > 0) as active_level_sum,
           sum(kills_leveled)                                    as kills_leveled,
           -- os mesmos números só dos abates afetados pelo dia sazonal (o rank_hunt_stats desconta)
           sum(kills) filter (where season_hit)                  as kills_season,
           count(distinct minute) filter (where season_hit)      as active_minutes_season,
           sum(xp) filter (where season_hit)                     as xp_season,
           sum(active_level_sum) filter (where season_hit and kills_leveled > 0) as active_level_sum_season,
           sum(kills_leveled) filter (where season_hit)          as kills_leveled_season
      from kmx
     group by 1, 2, 3
  ),
  dv as (
    -- fase 7: cada drop (com qty) vale a média do Mercado do último snapshot antes do fim da
    -- hora; sem média em ouro, o npc_price; fora do catálogo, nada (conta em drops_unpriced)
    select k.account_id, k.hour, k.hunt_slug,
           sum(q.qty)                                              as units,
           -- gemas: o menor entre a média de 7 dias e o menor anúncio aberto (o preço de venda real);
           -- as pedras ficam de fora: não são fonte de gemas (docs/design/painel-ux-v2.md)
           sum(q.qty * coalesce(least(po.avg, ask.min_price), po.avg, 0))
             filter (where gi.category is distinct from 'stone') as value_orb,
           sum(q.qty * coalesce(pg.avg, gi.npc_price, 0))          as value_gold,
           coalesce(sum(q.qty) filter (where gi.item_id is null), 0) as unpriced
      from kmx k
      cross join lateral jsonb_array_elements(
             case when jsonb_typeof(k.drops) = 'array' then k.drops else '[]'::jsonb end) d
      cross join lateral (
             select coalesce(nullif(d->>'qty', '')::numeric, 1) as qty, d->>'name' as name) q
      left join lateral (
             select i.item_id, i.npc_price, i.category from public.game_items i
              where i.name = q.name order by i.item_id limit 1) gi on true
      left join lateral (
             select max(m.taken_at) as taken_at from public.market_prices m
              where m.taken_at < k.hour + interval '1 hour') s on true
      left join lateral (
             select m.avg from public.market_prices m
              where m.taken_at = s.taken_at and m.item_id = gi.item_id and m.currency = 'orb') po on true
      left join lateral (
             select m.avg from public.market_prices m
              where m.taken_at = s.taken_at and m.item_id = gi.item_id and m.currency = 'gold') pg on true
      left join lateral (
             select a.min_price from public.market_asks a
              where a.item_id = gi.item_id and a.currency = 'orb'
                and a.taken_at < k.hour + interval '1 hour'
                and a.taken_at >= k.hour - interval '6 hours'
              order by a.taken_at desc limit 1) ask on true
     group by 1, 2, 3
  ),
  eagg as (
    select e.account_id,
           date_trunc('hour', e.received_at)          as hour,
           coalesce(e.data->>'hunt_slug', '')         as hunt_slug,
           count(*) filter (where e.type = 'capture_attempt')  as capture_attempts,
           count(*) filter (where e.type = 'pokemon.captured') as captures,
           count(*) filter (where e.type = 'pokemon.captured'
                              and coalesce((e.data->>'shiny')::boolean, false)) as shinies,
           count(*) filter (where e.type = 'pokecenter')           as pokecenter,
           count(*) filter (where e.type = 'session.disconnected') as disconnects,
           -- bolas lançadas (as poções e os revives vêm de kagg)
           coalesce(sum((e.data->>'ball_price')::numeric) filter (where e.type = 'capture_attempt'), 0)
             as balls_gold,
           -- fase 3b: espécie nova na semana do Top Catch
           count(*) filter (where e.type = 'rank.catch'
                              and coalesce((e.data->>'scores')::boolean, false)) as rank_points
      from public.events e
     where e.received_at >= v_from and e.received_at < v_to
       and e.type in ('capture_attempt', 'pokemon.captured', 'pokecenter', 'session.disconnected', 'rank.catch')
     group by 1, 2, 3
  ),
  keys as (
    select account_id, hour, hunt_slug from kagg
    union
    select account_id, hour, hunt_slug from eagg
  ),
  a as (
    select k.account_id, k.hour, k.hunt_slug,
           ka.kills, ka.xp, ka.gold, ka.active_minutes,
           ea.capture_attempts, ea.captures, ea.shinies, ea.pokecenter, ea.disconnects, ea.rank_points,
           -- custo dos consumíveis: bolas lançadas + poções e revives gastos
           coalesce(ea.balls_gold, 0) + coalesce(ka.items_gold, 0) as consumables_gold,
           ka.active_level_sum, ka.kills_leveled,
           ka.kills_season, ka.active_minutes_season, ka.xp_season,
           ka.active_level_sum_season, ka.kills_leveled_season
      from keys k
      left join kagg ka on ka.account_id = k.account_id and ka.hour = k.hour and ka.hunt_slug = k.hunt_slug
      left join eagg ea on ea.account_id = k.account_id and ea.hour = k.hour and ea.hunt_slug = k.hunt_slug
  )
  select a.account_id, a.hour, a.hunt_slug, v.metric, v.value
    from a
    left join dv on dv.account_id = a.account_id and dv.hour = a.hour and dv.hunt_slug = a.hunt_slug
    cross join lateral (values
      ('kills', a.kills::numeric), ('xp', a.xp), ('gold', a.gold), ('drops', dv.units),
      ('capture_attempts', a.capture_attempts::numeric), ('captures', a.captures::numeric),
      ('shinies', a.shinies::numeric),
      ('pokecenter', a.pokecenter::numeric), ('disconnects', a.disconnects::numeric),
      ('active_minutes', a.active_minutes::numeric),
      ('consumables_gold', a.consumables_gold),
      ('gold_net', coalesce(a.gold, 0) - a.consumables_gold),
      ('rank_points', a.rank_points::numeric),
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

-- ---------------------------------------------------------------------------
-- Recalcula as horas que receberam eventos ou minutos de abate desde a última passada.
-- ---------------------------------------------------------------------------
create or replace function public.refresh_metrics_incremental()
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_last  timestamptz;
  v_now   timestamptz := now();
  v_hour  timestamptz;
  v_hours int := 0;
begin
  select watermark into v_last from public.metric_refresh_state for update;

  -- 10 min de folga: transações que gravaram antes do watermark mas
  -- confirmaram depois. Reprocessar é idempotente.
  for v_hour in
    select date_trunc('hour', received_at)
      from public.events
     where inserted_at > v_last - interval '10 minutes'
       and inserted_at <= v_now
    union
    select date_trunc('hour', minute)
      from public.kill_minute
     where inserted_at > v_last - interval '10 minutes'
       and inserted_at <= v_now
     order by 1
  loop
    perform public.refresh_metric_hourly(v_hour, v_hour);
    v_hours := v_hours + 1;
  end loop;

  update public.metric_refresh_state set watermark = v_now;
  return v_hours;
end;
$$;

-- ---------------------------------------------------------------------------
-- Retenção: kill_minute fica 14 dias (a tela do Mercado e a liquidez olham 7); o resto como antes.
-- ---------------------------------------------------------------------------
create or replace function public.prune_events()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_noise bigint;
  v_old bigint;
  v_minutes bigint;
begin
  -- plano Free (500 MB): kill/capture/item.consumed ficam 1 dia; os agregados ficam em metric_hourly
  delete from public.events
   where (type in ('state.patch', 'battle.cura', 'wild_fled', 'action.sent', 'unknown')
          and received_at < now() - interval '2 days')
      or (type in ('kill', 'capture_attempt', 'item.consumed')
          and received_at < now() - interval '1 day');
  get diagnostics v_noise = row_count;
  delete from public.events where received_at < now() - interval '30 days';
  get diagnostics v_old = row_count;
  delete from public.kill_minute where minute < now() - interval '14 days';
  get diagnostics v_minutes = row_count;
  return v_noise + v_old + v_minutes;
end;
$$;
