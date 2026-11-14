-- Fase 3b, passo 4: entradas do plugin rank (docs/design/fase-3b-plugin-rank.md, seção 6).
--
-- Por hunt da conta, desde p_since:
--   kills, active_minutes : somas do metric_hourly (o agregado já existe; ler os
--                           abates brutos seria pesado demais).
--   last_chance, last_ball_id : o capture_attempt com `chance` mais recente.
-- Só a service_role executa.

create function public.rank_hunt_stats(p_account uuid, p_since timestamptz)
returns table (
  hunt_slug      text,
  kills          numeric,
  active_minutes numeric,
  last_chance    double precision,
  last_ball_id   int
)
language sql
stable
security definer
set search_path = ''
as $$
  with m as (
    select h.hunt_slug,
           coalesce(sum(h.value) filter (where h.metric = 'kills'), 0)          as kills,
           coalesce(sum(h.value) filter (where h.metric = 'active_minutes'), 0) as active_minutes
      from public.metric_hourly h
     where h.account_id = p_account
       and h.hunt_slug <> ''
       and h.hour >= date_trunc('hour', p_since)
       and h.metric in ('kills', 'active_minutes')
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
         c.last_ball_id
    from m
    full join c on c.hunt_slug = m.hunt_slug;
$$;

revoke all on function public.rank_hunt_stats(uuid, timestamptz) from public, anon, authenticated;
grant execute on function public.rank_hunt_stats(uuid, timestamptz) to service_role;
