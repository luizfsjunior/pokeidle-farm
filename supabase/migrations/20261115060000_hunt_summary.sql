-- Painel de hunts: totais por hunt desde p_since (uma conta ou todas as do dono).
-- security invoker: o RLS do metric_hourly limita às contas do dono.

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
  last_hour         timestamptz
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
         max(m.hour)
    from public.metric_hourly m
   where m.hour >= date_trunc('hour', p_since)
     and m.hunt_slug <> ''
     and (p_account is null or m.account_id = p_account)
   group by m.hunt_slug;
$$;

revoke all on function public.hunt_summary(timestamptz, uuid) from public, anon;
grant execute on function public.hunt_summary(timestamptz, uuid) to authenticated, service_role;
