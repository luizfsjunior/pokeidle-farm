-- Épico 0 do plano de 26/11 (folga no banco): bolas lançadas somadas por minuto e retenção mais justa.
-- Ver docs/design/retencao-eventos.md, "26/11: bolas por minuto".
--
-- Em 26/11 o banco tinha 390 MB de 500, 349 MB só na events. Nas últimas 24 h, três tipos eram quase tudo:
-- action.sent (66 mil, 63 mil deles de ball.throw), capture_attempt (61 mil) e wild_fled (60 mil).
-- O worker novo:
--   - soma os capture_attempt por minuto em kill_minute (tentativas, sucessos, ouro em bolas, última chance);
--   - deixa de gravar wild_fled (nada lia do banco) e o action.sent de ball.throw (repetia o capture_attempt).
--
-- As leituras (refresh_metric_hourly, rank_hunt_stats) somam kill_minute com os capture_attempt que ainda
-- estão em events, então o worker antigo continua funcionando até ser atualizado.
--
-- Esta migration não apaga nada por si: muda o prune_events(), que roda às 04:23 UTC pelo pg_cron.

alter table public.kill_minute
  add column capture_attempts  int              not null default 0,
  add column capture_successes int              not null default 0,
  add column balls_gold        bigint           not null default 0,   -- ouro gasto em bolas
  add column last_chance       double precision,                      -- a última chance vista no minuto
  add column last_ball_id      int;                                   -- a bola dessa chance

-- só as linhas com bola: o rank_hunt_stats procura a última chance por hunt
create index kill_minute_chance on public.kill_minute (account_id, hunt_slug, minute desc)
  where last_chance is not null;

-- ---------------------------------------------------------------------------
-- Métricas por hora: capture_attempts e o ouro em bolas passam a vir do mesmo lugar dos abates (kill_minute
-- e, na transição, events). As métricas e os nomes são os mesmos de antes.
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
    -- abates, consumo e bolas: uma linha por minuto (kill_minute) ou por evento (worker antigo, em events)
    select k.account_id, k.minute, k.hunt_slug, k.active_species_id, k.season,
           k.kills, k.xp::numeric as xp, k.gold::numeric as gold,
           k.active_level_sum::numeric as active_level_sum, k.kills_leveled,
           k.drops, k.consumables_gold::numeric as consumables_gold,
           k.capture_attempts, k.balls_gold::numeric as balls_gold
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
                then coalesce((e.data->>'qty')::numeric * (e.data->>'unit_price')::numeric, 0) else 0 end,
           (e.type = 'capture_attempt')::int,
           case when e.type = 'capture_attempt' then coalesce((e.data->>'ball_price')::numeric, 0) else 0 end
      from public.events e
     where e.type in ('kill', 'item.consumed', 'capture_attempt')
       and e.received_at >= v_from and e.received_at < v_to
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
           sum(capture_attempts)                                 as capture_attempts,
           sum(balls_gold)                                       as balls_gold,
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
           count(*) filter (where e.type = 'pokemon.captured') as captures,
           count(*) filter (where e.type = 'pokemon.captured'
                              and coalesce((e.data->>'shiny')::boolean, false)) as shinies,
           count(*) filter (where e.type = 'pokecenter')           as pokecenter,
           count(*) filter (where e.type = 'session.disconnected') as disconnects,
           -- fase 3b: espécie nova na semana do Top Catch
           count(*) filter (where e.type = 'rank.catch'
                              and coalesce((e.data->>'scores')::boolean, false)) as rank_points
      from public.events e
     where e.received_at >= v_from and e.received_at < v_to
       and e.type in ('pokemon.captured', 'pokecenter', 'session.disconnected', 'rank.catch')
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
           ka.capture_attempts, ea.captures, ea.shinies, ea.pokecenter, ea.disconnects, ea.rank_points,
           -- custo dos consumíveis: bolas lançadas + poções e revives gastos
           coalesce(ka.balls_gold, 0) + coalesce(ka.items_gold, 0) as consumables_gold,
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
-- Ritmo e última chance de captura por hunt (plugin rank): a chance vem de kill_minute ou de events.
-- ---------------------------------------------------------------------------
create or replace function public.rank_hunt_stats(p_account uuid, p_since timestamptz)
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
  attempts as (
    -- worker novo: a última chance de cada minuto; o minuto inteiro conta como o seu último segundo
    select k.hunt_slug, k.minute + interval '59.999 seconds' as at, k.part as part,
           k.last_chance, k.last_ball_id
      from public.kill_minute k
     where k.account_id = p_account
       and k.last_chance is not null
       and k.minute >= date_trunc('minute', p_since)
       and k.hunt_slug <> ''
    union all
    -- worker antigo: um evento por bola
    select e.data->>'hunt_slug', e.received_at, 0,
           (e.data->>'chance')::double precision,
           case when jsonb_typeof(e.data->'ball_id') = 'number' then (e.data->>'ball_id')::int end
      from public.events e
     where e.account_id = p_account
       and e.type = 'capture_attempt'
       and e.received_at >= p_since
       and jsonb_typeof(e.data->'chance') = 'number'
       and coalesce(e.data->>'hunt_slug', '') <> ''
  ),
  c as (
    select distinct on (a.hunt_slug) a.hunt_slug, a.last_chance, a.last_ball_id
      from attempts a
     order by a.hunt_slug, a.at desc, a.part desc
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

-- ---------------------------------------------------------------------------
-- Retenção. Mudanças:
--   - action.sent e action.blocked: 2 dias, menos os do Mercado que a página de Vendas lê por 30 dias
--     (market.criar, market.cancelar, market.meus; web/app/(painel)/economia/sales.ts). Antes o action.sent
--     do Mercado saía em 2 dias (a página perdia os cancelamentos) e o action.blocked de qualquer ação ficava
--     30 dias (103 mil linhas, 30 MB, quase todas de shop.buy com rate limit);
--   - unknown: 2 dias, menos os avisos do jogo que a página de Vendas lê por 30 dias (venda, marketComprado,
--     aviso, mktSorteio).
-- O resto continua como estava.
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
  delete from public.events
   where received_at < now() - interval '2 days'
     and (type in ('state.patch', 'battle.cura', 'wild_fled')
          or (type in ('action.sent', 'action.blocked')
              and coalesce(data->>'action', '') not in ('market.criar', 'market.cancelar', 'market.meus'))
          or (type = 'unknown'
              and coalesce(data->>'t', '') not in ('venda', 'marketComprado', 'aviso', 'mktSorteio')));
  get diagnostics v_noise = row_count;
  -- os volumosos do worker antigo (o novo soma em kill_minute)
  delete from public.events
   where type in ('kill', 'capture_attempt', 'item.consumed')
     and received_at < now() - interval '1 day';
  get diagnostics v_old = row_count;
  v_noise := v_noise + v_old;
  delete from public.events where received_at < now() - interval '30 days';
  get diagnostics v_old = row_count;
  delete from public.kill_minute where minute < now() - interval '14 days';
  get diagnostics v_minutes = row_count;
  return v_noise + v_old + v_minutes;
end;
$$;
