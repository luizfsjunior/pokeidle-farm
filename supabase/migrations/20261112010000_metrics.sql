-- 0002 — métricas em camadas (ver docs/decisions/0012).
--
--   events (bruto)  →  metric_hourly (base, por hora/conta/hunt)  →  metric_daily (view)
--                          ↑ metric_definitions (base e razões)
--   goals  →  goal_progress() (atual, ritmo, previsão, chance)  →  goal_snapshots (histórico)
--
-- Recalcular tudo de uma vez (ex.: depois de apagar eventos simulados):
--   select public.refresh_metric_hourly('2026-01-01', now());

-- ---------------------------------------------------------------------------
-- Eventos: quando a linha entrou no banco (o buffer do worker pode reenviar
-- eventos antigos; o refresh incremental se guia por esta coluna).
-- ---------------------------------------------------------------------------

alter table public.events add column inserted_at timestamptz not null default now();
create index events_inserted on public.events (inserted_at);

-- ---------------------------------------------------------------------------
-- Definições
-- ---------------------------------------------------------------------------

-- base: soma direta de metric_hourly. ratio: numerator / denominator × scale,
-- somando os dois no período antes de dividir (nunca média de médias).
create table public.metric_definitions (
  key          text primary key,
  label        text not null,
  unit         text not null default '',
  kind         text not null check (kind in ('base', 'ratio')),
  numerator    text references public.metric_definitions (key),
  denominator  text references public.metric_definitions (key),
  scale        numeric not null default 1,
  description  text not null default '',
  sort         int not null default 100,
  check ((kind = 'base' and numerator is null and denominator is null)
      or (kind = 'ratio' and numerator is not null and denominator is not null))
);

insert into public.metric_definitions (key, label, unit, kind, description, sort) values
  ('kills',            'Abates',                'abates', 'base', 'Pokémon selvagens derrotados.', 10),
  ('xp',               'XP',                    'xp',     'base', 'XP de treinador ganho nos abates.', 20),
  ('gold',             'Gold',                  'gold',   'base', 'Gold dos abates, incluindo venda automática.', 30),
  ('drops',            'Drops',                 'itens',  'base', 'Itens dropados nos abates.', 40),
  ('capture_attempts', 'Tentativas de captura', 'bolas',  'base', 'Bolas lançadas.', 50),
  ('captures',         'Capturas',              'pokémon','base', 'Capturas bem-sucedidas.', 60),
  ('shinies',          'Shinies',               'pokémon','base', 'Capturas shiny.', 70),
  ('pokecenter',       'Idas ao Centro',        'vezes',  'base', 'Equipe levada ao Centro Pokémon.', 80),
  ('disconnects',      'Quedas',                'vezes',  'base', 'Desconexões do worker.', 90),
  ('active_minutes',   'Minutos ativos',        'min',    'base', 'Minutos com pelo menos um abate.', 95);

insert into public.metric_definitions (key, label, unit, kind, numerator, denominator, scale, description, sort) values
  ('kills_per_hour',    'Abates por hora ativa',  'abates/h', 'ratio', 'kills',    'active_minutes',   60,  'Ritmo de abates enquanto farma.', 110),
  ('xp_per_hour',       'XP por hora ativa',      'xp/h',     'ratio', 'xp',       'active_minutes',   60,  '', 120),
  ('gold_per_hour',     'Gold por hora ativa',    'gold/h',   'ratio', 'gold',     'active_minutes',   60,  '', 130),
  ('captures_per_hour', 'Capturas por hora ativa','pokémon/h','ratio', 'captures', 'active_minutes',   60,  '', 140),
  ('capture_rate',      'Taxa de captura',        '%',        'ratio', 'captures', 'capture_attempts', 100, 'Capturas por bola lançada.', 150);

-- ---------------------------------------------------------------------------
-- Agregado por hora
-- ---------------------------------------------------------------------------

-- hunt_slug '' = evento sem hunt (quedas, Centro...).
create table public.metric_hourly (
  account_id  uuid not null references public.accounts (id) on delete cascade,
  hour        timestamptz not null,
  hunt_slug   text not null default '',
  metric      text not null references public.metric_definitions (key),
  value       numeric not null,
  primary key (account_id, hour, hunt_slug, metric)
);
create index metric_hourly_metric_hour on public.metric_hourly (metric, hour);

create table public.metric_refresh_state (
  id         boolean primary key default true check (id),
  watermark  timestamptz not null default '-infinity'
);
insert into public.metric_refresh_state default values;

-- Recalcula as horas de p_from até p_to (inclusive), para todas as contas.
-- Idempotente: apaga e reinsere. Base dos agregados = received_at.
create function public.refresh_metric_hourly(p_from timestamptz, p_to timestamptz)
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
             count(distinct date_trunc('minute', e.received_at)) filter (where e.type = 'kill') as active_minutes
        from public.events e
       where e.received_at >= v_from and e.received_at < v_to
       group by 1, 2, 3
    ) a
    cross join lateral (values
      ('kills', a.kills::numeric), ('xp', a.xp), ('gold', a.gold), ('drops', a.drops),
      ('capture_attempts', a.capture_attempts), ('captures', a.captures), ('shinies', a.shinies),
      ('pokecenter', a.pokecenter), ('disconnects', a.disconnects), ('active_minutes', a.active_minutes)
    ) v (metric, value)
   where v.value is not null and v.value <> 0;

  get diagnostics v_rows = row_count;
  return v_rows;
end;
$$;

-- Recalcula só as horas que receberam eventos desde a última execução
-- (inclusive eventos antigos reenviados pelo buffer). Roda pelo pg_cron.
create function public.refresh_metrics_incremental()
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
    select distinct date_trunc('hour', received_at)
      from public.events
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

-- Dia no fuso de Brasília.
create view public.metric_daily
with (security_invoker = true) as
select account_id,
       (hour at time zone 'America/Sao_Paulo')::date as day,
       hunt_slug,
       metric,
       sum(value) as value
  from public.metric_hourly
 group by 1, 2, 3, 4;

-- Série de uma métrica (base ou razão) por hora ou dia, opcionalmente
-- filtrada por conta e hunt. Respeita RLS (security invoker).
create function public.metric_series(
  p_metric  text,
  p_from    timestamptz,
  p_to      timestamptz,
  p_bucket  text default 'hour',
  p_account uuid default null,
  p_hunt    text default null
)
returns table (bucket timestamptz, value numeric)
language plpgsql
stable
set search_path = ''
as $$
declare
  d public.metric_definitions;
begin
  if p_bucket not in ('hour', 'day') then
    raise exception 'p_bucket deve ser hour ou day';
  end if;
  select * into d from public.metric_definitions where key = p_metric;
  if not found then
    raise exception 'métrica desconhecida: %', p_metric;
  end if;

  return query
  with h as (
    select case when p_bucket = 'hour' then m.hour
                else date_trunc('day', m.hour at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
           end as b,
           m.metric, m.value
      from public.metric_hourly m
     where m.hour >= p_from and m.hour < p_to
       and (p_account is null or m.account_id = p_account)
       and (p_hunt is null or m.hunt_slug = p_hunt)
       and m.metric in (p_metric, d.numerator, d.denominator)
  )
  select h.b,
         case when d.kind = 'base' then sum(h.value)
              else sum(h.value) filter (where h.metric = d.numerator) * d.scale
                   / nullif(sum(h.value) filter (where h.metric = d.denominator), 0)
         end
    from h
   group by h.b
   order by h.b;
end;
$$;

-- ---------------------------------------------------------------------------
-- Objetivos
-- ---------------------------------------------------------------------------

-- kind = 'metric':  somar `target` de uma métrica base (ex.: 1.000.000 de gold).
-- kind = 'capture': capturar `target` pokémon que batem com `filter`, ex.:
--   {"species": ["Dratini"], "min_quality": 1.5, "min_potency": 3,
--    "shiny": true, "min_iv_sum": 150, "min_ivs": {"atk": 28, "spe": 28}}
-- account_id nulo = todas as contas do dono.
create table public.goals (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name        text not null,
  kind        text not null check (kind in ('metric', 'capture')),
  account_id  uuid references public.accounts (id) on delete cascade,
  hunt_slug   text,
  metric      text references public.metric_definitions (key),
  filter      jsonb not null default '{}'::jsonb,
  target      numeric not null check (target > 0),
  starts_at   timestamptz not null default now(),
  deadline    timestamptz,
  status      text not null default 'active' check (status in ('active', 'done', 'archived')),
  created_at  timestamptz not null default now(),
  check ((kind = 'metric' and metric is not null) or (kind = 'capture' and metric is null)),
  check (deadline is null or deadline > starts_at)
);

create table public.goal_snapshots (
  goal_id             uuid not null references public.goals (id) on delete cascade,
  taken_at            timestamptz not null default now(),
  current             numeric not null,
  rate_per_hour       numeric,
  eta                 timestamptz,
  chance_by_deadline  numeric,
  primary key (goal_id, taken_at)
);

-- Um pokémon capturado (data de pokemon.captured) bate com o filtro?
create function public.capture_matches(p_data jsonb, p_filter jsonb)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select (p_filter->'species' is null
          or exists (select 1 from jsonb_array_elements_text(p_filter->'species') s
                      where lower(s) = lower(p_data->>'species')))
     and (p_filter->>'min_quality' is null
          or coalesce((p_data->>'quality')::numeric, 0) >= (p_filter->>'min_quality')::numeric)
     and (p_filter->>'min_potency' is null
          or coalesce((p_data->>'potency')::numeric, 0) >= (p_filter->>'min_potency')::numeric)
     and (p_filter->>'shiny' is null
          or coalesce((p_data->>'shiny')::boolean, false) = (p_filter->>'shiny')::boolean)
     and (p_filter->>'min_iv_sum' is null
          or coalesce((p_data->>'iv_sum')::numeric, 0) >= (p_filter->>'min_iv_sum')::numeric)
     and not exists (
           select 1 from jsonb_each_text(coalesce(p_filter->'min_ivs', '{}'::jsonb)) k
            where coalesce((p_data->'ivs'->>k.key)::numeric, 0) < k.value::numeric);
$$;

-- P(N ≥ k) com N ~ Poisson(λ).
create function public.poisson_at_least(p_k int, p_lambda numeric)
returns numeric
language plpgsql
immutable
set search_path = ''
as $$
declare
  v_term numeric;
  v_sum  numeric := 0;
  i      int;
begin
  if p_k <= 0 then return 1; end if;
  if p_lambda <= 0 then return 0; end if;
  v_term := exp(-p_lambda::double precision)::numeric;  -- P(N = 0)
  for i in 0 .. p_k - 1 loop
    v_sum := v_sum + v_term;
    v_term := v_term * p_lambda / (i + 1);
  end loop;
  return greatest(0, least(1, 1 - v_sum));
end;
$$;

-- Progresso de um objetivo agora.
--   rate_per_hour: ritmo por hora de relógio (inclui tempo parado) nas últimas 24 h.
--   Para capture, rate = capturas/h × p_match, onde p_match multiplica a
--   fração observada de cada critério nas capturas dos últimos 7 dias
--   (os sorteios são independentes; shiny usa 1/24000 dos Termos).
--   chance_by_deadline: chance de bater até o prazo mantendo o ritmo (Poisson),
--   só para capture.
create function public.goal_progress(p_goal uuid)
returns table (
  goal_id            uuid,
  current            numeric,
  target             numeric,
  pct                numeric,
  rate_per_hour      numeric,
  p_match            numeric,
  eta                timestamptz,
  on_track           boolean,
  chance_by_deadline numeric
)
language plpgsql
stable
set search_path = ''
as $$
declare
  g          public.goals;
  v_accounts uuid[];
  v_current  numeric;
  v_rate     numeric;
  v_p        numeric;
  v_first    timestamptz;
  v_hours    numeric;
  v_sum      numeric;
  v_total    numeric;
  v_frac     numeric;
  v_left     numeric;
  v_eta      timestamptz;
  v_chance   numeric;
  v_part     jsonb;
  v_key      text;
  v_end      timestamptz;
begin
  select * into g from public.goals where id = p_goal;
  if not found then
    return;
  end if;
  v_end := least(now(), coalesce(g.deadline, now()));

  select array_agg(a.id) into v_accounts
    from public.accounts a
   where a.owner_id = g.owner_id and (g.account_id is null or a.id = g.account_id);

  if g.kind = 'metric' then
    if (select kind from public.metric_definitions where key = g.metric) <> 'base' then
      raise exception 'objetivo de métrica precisa de uma métrica base (% é razão)', g.metric;
    end if;
    select coalesce(sum(m.value), 0) into v_current
      from public.metric_hourly m
     where m.account_id = any (v_accounts) and m.metric = g.metric
       and (g.hunt_slug is null or m.hunt_slug = g.hunt_slug)
       and m.hour >= date_trunc('hour', g.starts_at) and m.hour < v_end;

    select coalesce(sum(m.value), 0), min(m.hour) into v_sum, v_first
      from public.metric_hourly m
     where m.account_id = any (v_accounts) and m.metric = g.metric
       and (g.hunt_slug is null or m.hunt_slug = g.hunt_slug)
       and m.hour >= now() - interval '24 hours';
    v_hours := greatest(1, extract(epoch from now() - coalesce(v_first, now())) / 3600);
    v_rate := v_sum / v_hours;
  else
    select count(*) into v_current
      from public.events e
     where e.account_id = any (v_accounts) and e.type = 'pokemon.captured'
       and e.received_at >= g.starts_at and e.received_at < v_end
       and (g.hunt_slug is null or e.data->>'hunt_slug' = g.hunt_slug)
       and public.capture_matches(e.data, g.filter);

    -- capturas por hora de relógio, últimas 24 h
    select coalesce(sum(m.value), 0), min(m.hour) into v_sum, v_first
      from public.metric_hourly m
     where m.account_id = any (v_accounts) and m.metric = 'captures'
       and (g.hunt_slug is null or m.hunt_slug = g.hunt_slug)
       and m.hour >= now() - interval '24 hours';
    v_hours := greatest(1, extract(epoch from now() - coalesce(v_first, now())) / 3600);

    -- p_match: produto das frações de cada critério
    select count(*) into v_total
      from public.events e
     where e.account_id = any (v_accounts) and e.type = 'pokemon.captured'
       and e.received_at >= now() - interval '7 days'
       and (g.hunt_slug is null or e.data->>'hunt_slug' = g.hunt_slug);

    v_p := 1;
    for v_key in select jsonb_object_keys(g.filter) loop
      if v_key = 'min_ivs' then
        continue;
      elsif v_key = 'shiny' then
        v_p := v_p * case when (g.filter->>'shiny')::boolean then 1.0 / 24000 else 1 - 1.0 / 24000 end;
        continue;
      end if;
      v_part := jsonb_build_object(v_key, g.filter->v_key);
      v_frac := public._capture_fraction(v_accounts, g.hunt_slug, v_part, v_total);
      v_p := v_p * v_frac;
    end loop;
    for v_key in select jsonb_object_keys(coalesce(g.filter->'min_ivs', '{}'::jsonb)) loop
      v_part := jsonb_build_object('min_ivs', jsonb_build_object(v_key, g.filter->'min_ivs'->v_key));
      v_frac := public._capture_fraction(v_accounts, g.hunt_slug, v_part, v_total);
      v_p := v_p * v_frac;
    end loop;

    v_rate := (v_sum / v_hours) * v_p;
  end if;

  v_left := greatest(g.target - v_current, 0);
  if v_left = 0 then
    v_eta := null;
  elsif v_rate > 0 then
    v_eta := now() + make_interval(secs => (v_left / v_rate * 3600)::double precision);
  end if;

  if g.kind = 'capture' and g.deadline is not null then
    v_chance := case when v_left = 0 then 1
                     when g.deadline <= now() then 0
                     else public.poisson_at_least(
                            ceil(v_left)::int,
                            v_rate * extract(epoch from g.deadline - now()) / 3600)
                end;
  end if;

  return query select
    g.id, v_current, g.target,
    least(100, round(100 * v_current / g.target, 2)),
    round(v_rate, 6),
    case when g.kind = 'capture' then v_p end,
    v_eta,
    case when g.deadline is null then null
         when v_left = 0 then true
         else v_eta is not null and v_eta <= g.deadline end,
    round(v_chance, 4);
end;
$$;

-- Fração (suavizada) das capturas da janela de 7 dias que batem com um critério.
-- Suavização (x + 0,5) / (n + 1) para um critério nunca visto não zerar a previsão.
create function public._capture_fraction(p_accounts uuid[], p_hunt text, p_part jsonb, p_total numeric)
returns numeric
language sql
stable
set search_path = ''
as $$
  select (count(*) + 0.5) / (p_total + 1)
    from public.events e
   where e.account_id = any (p_accounts) and e.type = 'pokemon.captured'
     and e.received_at >= now() - interval '7 days'
     and (p_hunt is null or e.data->>'hunt_slug' = p_hunt)
     and public.capture_matches(e.data, p_part);
$$;

-- Grava o progresso de todos os objetivos ativos e marca os concluídos.
create function public.snapshot_goals()
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_rows int;
begin
  insert into public.goal_snapshots (goal_id, taken_at, current, rate_per_hour, eta, chance_by_deadline)
  select p.goal_id, now(), p.current, p.rate_per_hour, p.eta, p.chance_by_deadline
    from public.goals g
    cross join lateral public.goal_progress(g.id) p
   where g.status = 'active'
  on conflict do nothing;
  get diagnostics v_rows = row_count;

  update public.goals g
     set status = 'done'
    from public.goal_snapshots s
   where s.goal_id = g.id and s.taken_at = now()
     and g.status = 'active' and s.current >= g.target;

  return v_rows;
end;
$$;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table public.metric_definitions   enable row level security;
alter table public.metric_hourly        enable row level security;
alter table public.metric_refresh_state enable row level security;
alter table public.goals                enable row level security;
alter table public.goal_snapshots       enable row level security;

create policy read_definitions on public.metric_definitions
  for select to authenticated using (true);

create policy own_metric_hourly on public.metric_hourly
  for select to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())));

create policy own_goals on public.goals
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (
    owner_id = (select auth.uid())
    and (account_id is null
         or account_id in (select id from public.accounts where owner_id = (select auth.uid())))
  );

create policy own_goal_snapshots on public.goal_snapshots
  for select to authenticated
  using (goal_id in (select id from public.goals where owner_id = (select auth.uid())));

-- Recalcular é coisa do worker e do cron; ler progresso é do painel também.
revoke all on function public.refresh_metric_hourly(timestamptz, timestamptz) from public, anon, authenticated;
revoke all on function public.refresh_metrics_incremental()                    from public, anon, authenticated;
revoke all on function public.snapshot_goals()                                 from public, anon, authenticated;
grant execute on function public.refresh_metric_hourly(timestamptz, timestamptz) to service_role;
grant execute on function public.refresh_metrics_incremental()                    to service_role;
grant execute on function public.snapshot_goals()                                 to service_role;

revoke all on function public.goal_progress(uuid) from public, anon;
revoke all on function public.metric_series(text, timestamptz, timestamptz, text, uuid, text) from public, anon;
revoke all on function public._capture_fraction(uuid[], text, jsonb, numeric) from public, anon;
grant execute on function public.goal_progress(uuid) to authenticated, service_role;
grant execute on function public.metric_series(text, timestamptz, timestamptz, text, uuid, text) to authenticated, service_role;
grant execute on function public._capture_fraction(uuid[], text, jsonb, numeric) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Agendamento (pg_cron, se disponível; no Supabase é).
-- ---------------------------------------------------------------------------

do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    create extension if not exists pg_cron with schema pg_catalog;
    perform cron.schedule('metrics-refresh', '*/10 * * * *', 'select public.refresh_metrics_incremental()');
    perform cron.schedule('goal-snapshots',  '7 * * * *',    'select public.snapshot_goals()');
  end if;
end;
$$;
