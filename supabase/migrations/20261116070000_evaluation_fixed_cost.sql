-- Compensa?: custo fixo mensal (VPS e proxy) além da energia (16/11/2026).
-- Desde 16/11 o worker roda num droplet com proxy (ADR 0013), ~US$ 10/mês, e não mais só no PC de casa.

alter table public.evaluation_settings
  add column fixed_cost_usd numeric check (fixed_cost_usd is null or fixed_cost_usd >= 0);

comment on column public.evaluation_settings.fixed_cost_usd is
  'Custo fixo por mês em US$ (VPS, proxy). Soma com a energia no cost_usd do evaluation_summary.';

create or replace function public.evaluation_summary(p_days int default 7)
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
