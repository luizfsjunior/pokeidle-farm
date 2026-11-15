-- Fase 8: "Compensa?" (docs/design/fase-8-compensa.md).
--
-- evaluation_settings   : parâmetros de custo de energia, um por dono (o painel edita).
-- evaluation_summary    : projeção do mês por conta, o total e a estimativa "com 3 contas".
-- evaluation_liquidity  : quanto do que o Mercado vende na semana as contas dropam, por item.
--
-- As duas funções são security invoker: leem só as contas do dono pelo RLS.

create table public.evaluation_settings (
  owner_id       uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  machine_watts  numeric check (machine_watts is null or machine_watts >= 0),
  marginal       boolean not null default false,
  kwh_price_brl  numeric check (kwh_price_brl is null or kwh_price_brl >= 0),
  usd_brl        numeric check (usd_brl is null or usd_brl > 0),
  window_days    int not null default 7 check (window_days between 1 and 30),
  updated_at     timestamptz not null default now()
);

alter table public.evaluation_settings enable row level security;

create policy own_evaluation_settings on public.evaluation_settings
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

-- Comissão de venda de item em gemas (TAXA_ORB_PLANA do shared/taxa-mercado.mjs do jogo) e o
-- preço de recompra da gema (regras-do-jogo.md, seção 12).
create function public.evaluation_constants()
returns table (orb_fee numeric, usd_per_orb numeric)
language sql
immutable
as $$ select 0.15::numeric, 0.009::numeric $$;

create function public.evaluation_summary(p_days int default 7)
returns table (
  kind               text,     -- 'account' | 'total' | 'three_accounts'
  account_id         uuid,
  nick               text,
  gems               numeric,  -- drops_value_orb na janela
  gold               numeric,  -- drops_value_gold na janela (informativo)
  active_hours       numeric,
  data_days          numeric,  -- dias desde o primeiro abate na janela (até p_days)
  gems_per_day       numeric,
  gems_per_hour      numeric,
  month_gems_as_is   numeric,  -- por dia corrido × 30
  month_gems_24h     numeric,  -- por hora ativa × 24 × 30
  income_usd_as_is   numeric,
  income_usd_24h     numeric,
  cost_usd           numeric,  -- só no total e no "com 3 contas"; nulo se desconhecido
  profit_usd_as_is   numeric,
  profit_usd_24h     numeric
)
language plpgsql
stable
security invoker
set search_path = ''
as $$
declare
  v_now    timestamptz := date_trunc('hour', now()) + interval '1 hour';
  v_start  timestamptz := date_trunc('hour', now()) - make_interval(days => p_days);
  v_fee    numeric;
  v_usd    numeric;
  v_cost   numeric;
  s        public.evaluation_settings;
begin
  select c.orb_fee, c.usd_per_orb into v_fee, v_usd from public.evaluation_constants() c;

  select * into s from public.evaluation_settings where owner_id = (select auth.uid());
  if found and s.marginal then
    v_cost := 0;
  elsif found and s.machine_watts is not null and s.kwh_price_brl is not null and s.usd_brl is not null then
    v_cost := s.machine_watts / 1000 * 24 * 30 * s.kwh_price_brl / s.usd_brl;
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

create function public.evaluation_liquidity(p_days int default 7)
returns table (
  name          text,
  item_id       bigint,
  dropped       numeric,  -- unidades dropadas na janela
  dropped_week  numeric,  -- por semana
  sold_week     numeric,  -- unidades vendidas por semana no Mercado (gemas, último snapshot)
  share         numeric,  -- dropped_week / sold_week
  flagged       boolean   -- share acima de 10%
)
language sql
stable
security invoker
set search_path = ''
as $$
  with drops as (
    select d->>'name' as name, sum(coalesce(nullif(d->>'qty', '')::numeric, 1)) as qty
      from public.events e
      cross join lateral jsonb_array_elements(
             case when jsonb_typeof(e.data->'drops') = 'array' then e.data->'drops' else '[]'::jsonb end) d
     where e.type = 'kill' and e.received_at >= now() - make_interval(days => p_days)
     group by 1
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

revoke all on function public.evaluation_summary(int)   from public, anon;
revoke all on function public.evaluation_liquidity(int) from public, anon;
grant execute on function public.evaluation_constants()  to authenticated, service_role;
grant execute on function public.evaluation_summary(int)   to authenticated, service_role;
grant execute on function public.evaluation_liquidity(int) to authenticated, service_role;
