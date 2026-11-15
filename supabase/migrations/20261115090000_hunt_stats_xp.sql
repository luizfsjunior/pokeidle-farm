-- Foco XP (docs/design/foco-xp.md): o rank_hunt_stats devolve também a XP por hunt, para a
-- XP por abate medida (já com os bônus de VIP, evento etc.).

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
           coalesce(sum(h.value) filter (where h.metric = 'kills'), 0)          as kills,
           coalesce(sum(h.value) filter (where h.metric = 'active_minutes'), 0) as active_minutes,
           sum(h.value) filter (where h.metric = 'active_level_sum')
             / nullif(sum(h.value) filter (where h.metric = 'kills_leveled'), 0) as avg_active_level,
           coalesce(sum(h.value) filter (where h.metric = 'xp'), 0) as xp
      from public.metric_hourly h
     where h.account_id = p_account
       and h.hunt_slug <> ''
       and h.hour >= date_trunc('hour', p_since)
       and h.metric in ('kills', 'active_minutes', 'active_level_sum', 'kills_leveled', 'xp')
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
