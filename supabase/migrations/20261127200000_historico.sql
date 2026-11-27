-- Épico D: números e histórico no painel (docs/design/historico.md).
--
-- O histórico por dia sai de metric_hourly (já agregado por hora, conta e hunt), nunca de eventos crus.
-- Para o banco não crescer sem fim, as horas com mais de 100 dias viram uma linha por dia e métrica em
-- metric_day (sem hunt) e saem de metric_hourly. Corte fixo: dia de Brasília com mais de 95 dias vem de
-- metric_day; o resto, de metric_hourly. Os 5 dias de folga cobrem um arquivamento que falhou numa noite.

-- 1. Arquivo diário -----------------------------------------------------------------------------------

create table public.metric_day (
  account_id uuid not null references public.accounts (id) on delete cascade,
  day        date not null, -- dia de Brasília
  metric     text not null,
  value      numeric not null,
  primary key (account_id, day, metric)
);

alter table public.metric_day enable row level security;
create policy own_metric_day on public.metric_day
  for select to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())));
grant select on public.metric_day to authenticated;
grant all on public.metric_day to service_role;

-- Arquiva os dias com mais de 95 dias (idempotente) e apaga de metric_hourly as horas com mais de 100.
create or replace function public.archive_metric_hourly()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_cut  date := (now() at time zone 'America/Sao_Paulo')::date - 95;
  v_gone integer;
begin
  insert into public.metric_day (account_id, day, metric, value)
  select account_id, (hour at time zone 'America/Sao_Paulo')::date, metric, sum(value)
    from public.metric_hourly
   where hour < (v_cut::timestamp at time zone 'America/Sao_Paulo')
   group by 1, 2, 3
  on conflict (account_id, day, metric) do update set value = excluded.value;

  delete from public.metric_hourly where hour < now() - interval '100 days';
  get diagnostics v_gone = row_count;
  return v_gone;
end;
$$;

revoke all on function public.archive_metric_hourly() from public, anon, authenticated;
grant execute on function public.archive_metric_hourly() to service_role;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('metric-hourly-archive', '17 5 * * *', 'select public.archive_metric_hourly()');
  end if;
end $$;

-- 2. Histórico por conta e dia ------------------------------------------------------------------------

-- Uma linha por conta e dia de Brasília nos últimos p_days dias (hoje incluso): as métricas somadas de
-- todas as hunts e o retrato do perfil no fim do dia (account_profile_daily). Dia sem nada vem com zeros
-- nas métricas e nulos no perfil. Respeita RLS (security invoker; as tabelas filtram por account_id).
create or replace function public.account_history(p_days integer default 30)
returns table (
  account_id        uuid,
  day               date,
  kills             numeric,
  xp                numeric,
  gold              numeric,
  gold_net          numeric,
  consumables_gold  numeric,
  captures          numeric,
  capture_attempts  numeric,
  shinies           numeric,
  active_minutes    numeric,
  disconnects       numeric,
  pokecenter        numeric,
  drops_value_orb   numeric,
  level             integer,
  trainer_xp        numeric,
  gems              numeric,
  diamonds          numeric,
  dex_caught        integer,
  pokemon_count     integer
)
language sql
stable
security invoker
set search_path = ''
as $$
  with bounds as (
    select (now() at time zone 'America/Sao_Paulo')::date as today,
           (now() at time zone 'America/Sao_Paulo')::date - (least(greatest(p_days, 1), 400) - 1) as first,
           (now() at time zone 'America/Sao_Paulo')::date - 95 as cut
  ),
  m as (
    select h.account_id, (h.hour at time zone 'America/Sao_Paulo')::date as day, h.metric, h.value
      from public.metric_hourly h, bounds b
     where h.hour >= (greatest(b.first, b.cut)::timestamp at time zone 'America/Sao_Paulo')
       and h.metric in ('kills', 'xp', 'gold', 'gold_net', 'consumables_gold', 'captures', 'capture_attempts',
                        'shinies', 'active_minutes', 'disconnects', 'pokecenter', 'drops_value_orb')
    union all
    select d.account_id, d.day, d.metric, d.value
      from public.metric_day d, bounds b
     where d.day >= b.first and d.day < b.cut
  ),
  agg as (
    select m.account_id, m.day,
           sum(m.value) filter (where m.metric = 'kills')            as kills,
           sum(m.value) filter (where m.metric = 'xp')               as xp,
           sum(m.value) filter (where m.metric = 'gold')             as gold,
           sum(m.value) filter (where m.metric = 'gold_net')         as gold_net,
           sum(m.value) filter (where m.metric = 'consumables_gold') as consumables_gold,
           sum(m.value) filter (where m.metric = 'captures')         as captures,
           sum(m.value) filter (where m.metric = 'capture_attempts') as capture_attempts,
           sum(m.value) filter (where m.metric = 'shinies')          as shinies,
           sum(m.value) filter (where m.metric = 'active_minutes')   as active_minutes,
           sum(m.value) filter (where m.metric = 'disconnects')      as disconnects,
           sum(m.value) filter (where m.metric = 'pokecenter')       as pokecenter,
           sum(m.value) filter (where m.metric = 'drops_value_orb')  as drops_value_orb
      from m
     group by 1, 2
  ),
  grid as (
    select a.id as account_id, g::date as day
      from public.accounts a, bounds b, generate_series(b.first, b.today, interval '1 day') g
  )
  select g.account_id, g.day,
         coalesce(x.kills, 0), coalesce(x.xp, 0), coalesce(x.gold, 0), coalesce(x.gold_net, 0),
         coalesce(x.consumables_gold, 0), coalesce(x.captures, 0), coalesce(x.capture_attempts, 0),
         coalesce(x.shinies, 0), coalesce(x.active_minutes, 0), coalesce(x.disconnects, 0),
         coalesce(x.pokecenter, 0), coalesce(x.drops_value_orb, 0),
         p.level, p.xp, p.gems, p.diamonds, p.dex_caught, p.pokemon_count
    from grid g
    left join agg x on x.account_id = g.account_id and x.day = g.day
    left join public.account_profile_daily p on p.account_id = g.account_id and p.day = g.day
   order by g.account_id, g.day;
$$;

revoke all on function public.account_history(integer) from public, anon;
grant execute on function public.account_history(integer) to authenticated, service_role;

-- 3. hunt_summary com o XP (o painel de hunts mostra XP/h) --------------------------------------------

drop function public.hunt_summary(timestamptz, uuid);
create function public.hunt_summary(p_since timestamptz, p_account uuid default null)
returns table (
  hunt_slug         text,
  kills             numeric,
  active_minutes    numeric,
  gold              numeric,
  gold_net          numeric,
  consumables_gold  numeric,
  drops             numeric,
  drops_value_orb   numeric,
  drops_value_gold  numeric,
  capture_attempts  numeric,
  captures          numeric,
  shinies           numeric,
  rank_points       numeric,
  pokecenter        numeric,
  last_hour         timestamptz,
  xp                numeric
)
language sql
stable
security invoker
set search_path = ''
as $$
  select m.hunt_slug,
         coalesce(sum(m.value) filter (where m.metric = 'kills'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'active_minutes'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'gold'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'gold_net'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'consumables_gold'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'drops'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'drops_value_orb'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'drops_value_gold'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'capture_attempts'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'captures'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'shinies'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'rank_points'), 0),
         coalesce(sum(m.value) filter (where m.metric = 'pokecenter'), 0),
         max(m.hour),
         coalesce(sum(m.value) filter (where m.metric = 'xp'), 0)
    from public.metric_hourly m
   where m.hour >= date_trunc('hour', p_since)
     and m.hunt_slug <> ''
     and (p_account is null or m.account_id = p_account)
   group by m.hunt_slug;
$$;

revoke all on function public.hunt_summary(timestamptz, uuid) from public, anon;
grant execute on function public.hunt_summary(timestamptz, uuid) to authenticated, service_role;
