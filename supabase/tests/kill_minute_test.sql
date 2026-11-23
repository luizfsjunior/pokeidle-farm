-- Teste dos abates por minuto (docs/design/retencao-eventos.md, "Abates por minuto").
-- Os mesmos abates gravados de dois jeitos têm de dar as mesmas métricas: a conta A como eventos (worker
-- antigo), a conta B somada em kill_minute (worker novo). Cria os próprios dados (em 2001) e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values ('00000000-0000-0000-0000-0000000000e1');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-000000000e0a', '00000000-0000-0000-0000-0000000000e1', 'km-eventos', 'farm'),
  ('00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-0000000000e1', 'km-minutos', 'farm');
insert into public.game_species (species_id, name, type1, type2, stage) values
  (990101, 'Rochaz', 'ROCK', null, 'last'),
  (990102, 'Folhaz', 'GRASS', null, 'last');
insert into public.game_hunts (slug, name, level, species_id) values ('rochaz', 'Rochaz', 20, 990101);
insert into public.game_items (item_id, name, category, rare, npc_price, source) values
  (990201, 'Pena KM', 'loot', false, 300, 'json'),
  (990202, 'Pedra KM', 'stone', true, 700, 'json');
insert into public.market_prices (taken_at, item_id, currency, avg, units, days) values
  ('2001-11-12 09:30Z', 990201, 'orb', 2.5, 100, 7),
  ('2001-11-12 09:30Z', 990201, 'gold', 250, 100, 7),
  ('2001-11-12 09:30Z', 990202, 'orb', 40, 10, 7);

-- conta A: um evento por abate e por consumo
insert into public.events (id, account_id, session_id, type, received_at, data)
select gen_random_uuid(), '00000000-0000-0000-0000-000000000e0a', '00000000-0000-0000-0000-00000000005a',
       t, at::timestamptz, d::jsonb
  from (values
    ('kill', '2001-11-12 10:01:05Z', '{"hunt_slug":"rochaz","xp":100,"gold":40,"gold_autosell":5,"active_level":30,"active_species_id":990102,"season":"ROCK","drops":[{"name":"Pena KM","qty":2}]}'),
    ('kill', '2001-11-12 10:01:40Z', '{"hunt_slug":"rochaz","xp":100,"gold":40,"gold_autosell":0,"active_level":30,"active_species_id":990102,"season":"ROCK","drops":[{"name":"Pena KM","qty":1},{"name":"Pedra KM","qty":1}]}'),
    ('kill', '2001-11-12 10:02:10Z', '{"hunt_slug":"rochaz","xp":120,"gold":50,"gold_autosell":0,"active_level":null,"active_species_id":990102,"drops":[]}'),
    ('kill', '2001-11-12 10:59:59Z', '{"hunt_slug":"rochaz","xp":120,"gold":50,"gold_autosell":0,"active_level":31,"active_species_id":990102,"drops":[{"name":"Item Desconhecido KM","qty":3}]}'),
    ('kill', '2001-11-12 11:00:01Z', '{"xp":7,"gold":1,"gold_autosell":0,"drops":[]}'),
    ('item.consumed', '2001-11-12 10:01:50Z', '{"hunt_slug":"rochaz","item_id":200,"qty":2,"unit_price":26}'),
    ('capture_attempt', '2001-11-12 10:02:30Z', '{"hunt_slug":"rochaz","ball_price":10,"chance":0.1,"ball_id":1}')
  ) as v(t, at, d);

-- conta B: os mesmos abates, somados por minuto como a telemetria nova grava; a capture_attempt continua evento.
-- O minuto 10:01 chega em duas partes (a segunda é o abate que entrou depois do minuto já gravado).
insert into public.kill_minute (account_id, session_id, minute, hunt_slug, active_species_id, season, part,
                                kills, xp, gold, active_level_sum, kills_leveled, drops, consumables_gold)
values
  ('00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-00000000005b', '2001-11-12 10:01Z',
   'rochaz', 990102, 'ROCK', 0, 1, 100, 45, 30, 1, '[{"name":"Pena KM","qty":2}]', 0),
  ('00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-00000000005b', '2001-11-12 10:01Z',
   'rochaz', 990102, 'ROCK', 1, 1, 100, 40, 30, 1, '[{"name":"Pena KM","qty":1},{"name":"Pedra KM","qty":1}]', 0),
  ('00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-00000000005b', '2001-11-12 10:01Z',
   'rochaz', 0, '', 0, 0, 0, 0, 0, 0, '[]', 52),
  ('00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-00000000005b', '2001-11-12 10:02Z',
   'rochaz', 990102, '', 0, 1, 120, 50, 0, 0, '[]', 0),
  ('00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-00000000005b', '2001-11-12 10:59Z',
   'rochaz', 990102, '', 0, 1, 120, 50, 31, 1, '[{"name":"Item Desconhecido KM","qty":3}]', 0),
  ('00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-00000000005b', '2001-11-12 11:00Z',
   '', 0, '', 0, 1, 7, 1, 0, 0, '[]', 0);
insert into public.events (id, account_id, session_id, type, received_at, data) values
  (gen_random_uuid(), '00000000-0000-0000-0000-000000000e0b', '00000000-0000-0000-0000-00000000005b',
   'capture_attempt', '2001-11-12 10:02:30Z', '{"hunt_slug":"rochaz","ball_price":10,"chance":0.1,"ball_id":1}');

do $$
declare
  a constant uuid := '00000000-0000-0000-0000-000000000e0a';
  b constant uuid := '00000000-0000-0000-0000-000000000e0b';
  v_diff int;
  v numeric;
begin
  perform public.refresh_metric_hourly('2001-11-12 10:00Z', '2001-11-12 11:00Z');

  -- as duas contas têm exatamente as mesmas métricas
  select count(*) into v_diff from (
    (select hour, hunt_slug, metric, value from public.metric_hourly where account_id = a
     except select hour, hunt_slug, metric, value from public.metric_hourly where account_id = b)
    union all
    (select hour, hunt_slug, metric, value from public.metric_hourly where account_id = b
     except select hour, hunt_slug, metric, value from public.metric_hourly where account_id = a)
  ) x;
  assert v_diff = 0, format('%s métricas diferentes entre eventos e kill_minute', v_diff);

  -- e os números são os esperados (conta B)
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'kills';
  assert v = 4, format('kills %s ≠ 4', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'active_minutes';
  assert v = 3, format('active_minutes %s ≠ 3 (as duas partes de 10:01 são um minuto)', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'gold';
  assert v = 185, format('gold %s ≠ 185 (com a venda automática)', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'consumables_gold';
  assert v = 62, format('consumables_gold %s ≠ 62 (2 × 26 de poção + 10 de bola)', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'kills_season';
  assert v = 2, format('kills_season %s ≠ 2 (dia de Pedra numa hunt ROCK)', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'kills_leveled';
  assert v = 3, format('kills_leveled %s ≠ 3 (um abate sem nível)', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'drops_value_orb';
  assert v = 7.5, format('drops_value_orb %s ≠ 7.5 (3 penas × 2,5; a pedra fica fora das gemas)', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'drops_unpriced';
  assert v = 3, format('drops_unpriced %s ≠ 3', v);
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 11:00Z' and hunt_slug = '' and metric = 'kills';
  assert v = 1, format('kill sem hunt às 11h %s ≠ 1', v);

  -- drops por item: os dois jeitos dão o mesmo
  select count(*) into v_diff from (
    (select * from public.dropped_items('2001-11-12 00:00Z', a)
     except select * from public.dropped_items('2001-11-12 00:00Z', b))
    union all
    (select * from public.dropped_items('2001-11-12 00:00Z', b)
     except select * from public.dropped_items('2001-11-12 00:00Z', a))
  ) x;
  assert v_diff = 0, format('%s itens diferentes em dropped_items', v_diff);
  select qty into v from public.dropped_items('2001-11-12 00:00Z', b) where name = 'Pena KM';
  assert v = 3, format('Pena KM %s ≠ 3', v);
  select qty into v from public.dropped_items('2001-11-12 10:02Z', b) where name = 'Pena KM';
  assert v is null, 'dropped_items respeita o início da janela';

  -- o refresh incremental acha as horas que só têm kill_minute
  delete from public.metric_hourly where account_id = b;
  update public.kill_minute set inserted_at = now() where account_id = b;
  update public.metric_refresh_state set watermark = now() - interval '1 minute';
  perform public.refresh_metrics_incremental();
  select value into v from public.metric_hourly
   where account_id = b and hour = '2001-11-12 10:00Z' and hunt_slug = 'rochaz' and metric = 'kills';
  assert v = 4, format('refresh incremental: kills %s ≠ 4', v);

  -- retenção: kill_minute de mais de 14 dias sai
  perform public.prune_events();
  assert not exists (select 1 from public.kill_minute where account_id = b), 'kill_minute de 2001 deveria sair';

  delete from public.events where account_id in (a, b);
  delete from public.kill_minute where account_id in (a, b);
  delete from public.metric_hourly where account_id in (a, b);
  delete from public.market_prices where item_id in (990201, 990202);
  delete from public.game_items where item_id in (990201, 990202);
  delete from public.game_hunts where slug = 'rochaz';
  delete from public.game_species where species_id in (990101, 990102);
  delete from public.accounts where id in (a, b);
  delete from auth.users where id = '00000000-0000-0000-0000-0000000000e1';
  raise notice 'kill_minute: ok';
end;
$$;
