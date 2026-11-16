-- Teste do dia sazonal fora do ritmo medido (docs/design/simulador-4-decisoes.md).
-- Cria os próprios dados (em 2001) e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values ('00000000-0000-0000-0000-0000000000d1');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-000000000d01', '00000000-0000-0000-0000-0000000000d1', 'season-1', 'farm');
insert into public.game_species (species_id, name, type1, type2, stage) values
  (990001, 'Kabutoz', 'ROCK', 'WATER', 'first_of_three'),
  (990002, 'Bulbaz', 'GRASS', 'POISON', 'first_of_three'),
  (990003, 'Magiz', 'WATER', null, 'last');
insert into public.game_hunts (slug, name, level, species_id) values
  ('kabutoz', 'Kabutoz', 20, 990001), ('magiz', 'Magiz', 1, 990003);

-- 10h: 3 abates na Kabutoz num dia de Pedra (afetados: a hunt é ROCK), 2 na Magiz (não afetados:
-- nem a Magiz nem o ativo são ROCK) e 1 na Magiz num dia de Planta (afetado: o ativo é GRASS)
insert into public.events (id, account_id, session_id, type, received_at, data)
select gen_random_uuid(), '00000000-0000-0000-0000-000000000d01', gen_random_uuid(), 'kill', at::timestamptz, d::jsonb
  from (values
    ('2001-11-12 10:01Z', '{"hunt_slug":"kabutoz","xp":500,"active_level":30,"active_species_id":990002,"season":"ROCK"}'),
    ('2001-11-12 10:01Z', '{"hunt_slug":"kabutoz","xp":500,"active_level":30,"active_species_id":990002,"season":"ROCK"}'),
    ('2001-11-12 10:02Z', '{"hunt_slug":"kabutoz","xp":500,"active_level":30,"active_species_id":990002,"season":"ROCK"}'),
    ('2001-11-12 10:03Z', '{"hunt_slug":"magiz","xp":10,"active_level":30,"active_species_id":990002,"season":"ROCK"}'),
    ('2001-11-12 10:04Z', '{"hunt_slug":"magiz","xp":10,"active_level":30,"active_species_id":990002}'),
    ('2001-11-12 10:05Z', '{"hunt_slug":"magiz","xp":10,"active_level":31,"active_species_id":990002,"season":"grass"}')
  ) as v(at, d);

do $$
declare
  acc constant uuid := '00000000-0000-0000-0000-000000000d01';
  r record;
  v numeric;
begin
  perform public.refresh_metric_hourly('2001-11-12 10:00Z', '2001-11-12 10:00Z');
  select value into v from public.metric_hourly
   where account_id = acc and hunt_slug = 'kabutoz' and metric = 'kills';
  assert v = 3, format('kills totais da kabutoz %s ≠ 3 (não mudam)', v);
  select value into v from public.metric_hourly
   where account_id = acc and hunt_slug = 'kabutoz' and metric = 'kills_season';
  assert v = 3, format('kills_season da kabutoz %s ≠ 3', v);
  select value into v from public.metric_hourly
   where account_id = acc and hunt_slug = 'magiz' and metric = 'kills_season';
  assert v = 1, format('kills_season da magiz %s ≠ 1 (só o dia de Planta, pelo ativo)', v);

  -- o rank_hunt_stats desconta: a Kabutoz some do ritmo; a Magiz fica com 2 abates em 2 minutos
  select * into r from public.rank_hunt_stats(acc, '2001-11-12 09:00Z') where hunt_slug = 'kabutoz';
  assert r.kills = 0 and r.active_minutes = 0 and r.xp = 0, 'kabutoz fora do ritmo';
  select * into r from public.rank_hunt_stats(acc, '2001-11-12 09:00Z') where hunt_slug = 'magiz';
  assert r.kills = 2 and r.active_minutes = 2, format('magiz %s abates em %s min', r.kills, r.active_minutes);
  assert r.xp = 20 and r.avg_active_level = 30, format('magiz xp %s nível %s', r.xp, r.avg_active_level);

  delete from public.events where account_id = acc;
  delete from public.metric_hourly where account_id = acc;
  delete from public.game_hunts where slug in ('kabutoz', 'magiz');
  delete from public.game_species where species_id between 990001 and 990003;
  delete from public.accounts where nick = 'season-1';
  delete from auth.users where id = '00000000-0000-0000-0000-0000000000d1';
  raise notice 'season_pace: ok';
end;
$$;
