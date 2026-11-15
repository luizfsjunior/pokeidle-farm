-- Teste do "Compensa?" (fase 8; docs/design/fase-8-compensa.md, casos 1 a 7).
-- Cria os próprios donos, contas, métricas e preços e apaga tudo no fim.
\set ON_ERROR_STOP 1

-- dono A com duas contas, dono B com uma
insert into auth.users (id) values
  ('00000000-0000-0000-0000-0000000e0a01'), ('00000000-0000-0000-0000-0000000e0b02');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000e0ac001', '00000000-0000-0000-0000-0000000e0a01', 'aval-1', 'farm'),
  ('00000000-0000-0000-0000-00000e0ac002', '00000000-0000-0000-0000-0000000e0a01', 'aval-2', 'farm'),
  ('00000000-0000-0000-0000-00000e0bc001', '00000000-0000-0000-0000-0000000e0b02', 'aval-b', 'farm');

-- aval-1: 7 dias (168 horas) até a hora atual, 12 h ativas por dia (30 min por hora), 100 gemas por dia
insert into public.metric_hourly (account_id, hour, hunt_slug, metric, value)
select '00000000-0000-0000-0000-00000e0ac001', h, 'x', m.metric, m.value
  from generate_series(date_trunc('hour', now()) - interval '167 hours', date_trunc('hour', now()),
                       interval '1 hour') h
  cross join (values ('kills', 10::numeric), ('active_minutes', 30), ('drops_value_orb', 100.0 / 24),
                     ('drops_value_gold', 1000)) m (metric, value);

-- aval-2: só os últimos 3 dias (72 horas), 60 gemas por dia, 24 h ativas
insert into public.metric_hourly (account_id, hour, hunt_slug, metric, value)
select '00000000-0000-0000-0000-00000e0ac002', h, 'x', m.metric, m.value
  from generate_series(date_trunc('hour', now()) - interval '71 hours', date_trunc('hour', now()),
                       interval '1 hour') h
  cross join (values ('kills', 10::numeric), ('active_minutes', 60), ('drops_value_orb', 60.0 / 24)) m (metric, value);

-- aval-b (outro dono): não pode aparecer para o dono A
insert into public.metric_hourly (account_id, hour, hunt_slug, metric, value) values
  ('00000000-0000-0000-0000-00000e0bc001', date_trunc('hour', now()), 'x', 'drops_value_orb', 999999),
  ('00000000-0000-0000-0000-00000e0bc001', date_trunc('hour', now()), 'x', 'kills', 1);

-- liquidez: dois itens dropados na última semana pela aval-1
insert into public.game_items (item_id, name, npc_price, source) values
  (910001, 'Aval Pedra', 100, 'json'), (910002, 'Aval Pena', 10, 'json');
insert into public.market_prices (taken_at, item_id, currency, avg, units, days) values
  (now() - interval '1 minute', 910001, 'orb', 5, 100, 7),
  (now() - interval '1 minute', 910002, 'orb', 1, 1000, 7);
insert into public.events (id, account_id, session_id, type, received_at, data) values
  (gen_random_uuid(), '00000000-0000-0000-0000-00000e0ac001', gen_random_uuid(), 'kill', now() - interval '1 day',
   '{"drops": [{"name": "Aval Pedra", "qty": 20}, {"name": "Aval Pena", "qty": 20}]}');

set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000e0a01', false);

do $$
declare
  r record;
  t record;
  x record;
  near constant numeric := 0.01;
begin
  -- casos 1 e 2: aval-1
  select * into r from public.evaluation_summary(7) where nick = 'aval-1';
  assert abs(r.data_days - 7) < near, format('data_days %s ≠ 7', r.data_days);
  assert abs(r.gems_per_day - 100) < near, format('gems_per_day %s ≠ 100', r.gems_per_day);
  assert abs(r.gems_per_hour - 100.0 / 12) < near, format('gems_per_hour %s ≠ 8,33', r.gems_per_hour);
  assert abs(r.month_gems_as_is - 3000) < near, format('month_as_is %s ≠ 3000', r.month_gems_as_is);
  assert abs(r.month_gems_24h - 6000) < 0.1, format('month_24h %s ≠ 6000', r.month_gems_24h);
  assert abs(r.income_usd_as_is - 22.95) < near, format('income %s ≠ 22,95', r.income_usd_as_is);
  assert r.cost_usd is null, 'conta não tem custo próprio';

  -- caso 4: aval-2 com 3 dias de dado
  select * into r from public.evaluation_summary(7) where nick = 'aval-2';
  assert abs(r.data_days - 3) < near, format('data_days aval-2 %s ≠ 3', r.data_days);
  assert abs(r.gems_per_day - 60) < near, format('gems_per_day aval-2 %s ≠ 60', r.gems_per_day);

  -- caso 3: sem evaluation_settings → custo desconhecido, lucro = renda
  select * into t from public.evaluation_summary(7) where kind = 'total';
  assert t.cost_usd is null, 'custo deveria ser desconhecido sem settings';
  assert abs(t.profit_usd_as_is - t.income_usd_as_is) < near, 'lucro sem custo ≠ renda';

  -- caso 5: total e "com 3 contas"
  assert abs(t.gems_per_day - 160) < near, format('total por dia %s ≠ 160', t.gems_per_day);
  assert abs(t.month_gems_as_is - 4800) < 0.1, format('total mês %s ≠ 4800', t.month_gems_as_is);
  select * into x from public.evaluation_summary(7) where kind = 'three_accounts';
  assert abs(x.month_gems_as_is - 7200) < 0.1, format('3 contas %s ≠ 7200', x.month_gems_as_is);

  -- caso 6: o outro dono não aparece
  assert not exists (select 1 from public.evaluation_summary(7) where nick = 'aval-b'), 'conta alheia apareceu';
  assert (select count(*) from public.evaluation_summary(7) where kind = 'account') = 2, 'deveria ter 2 contas';

  -- caso 3: com parâmetros (60 W, R$ 0,90, câmbio 5) → US$ 7,776; marginal → 0; tarifa vazia → nulo
  insert into public.evaluation_settings (machine_watts, kwh_price_brl, usd_brl) values (60, 0.90, 5.0);
  select * into t from public.evaluation_summary(7) where kind = 'total';
  assert abs(t.cost_usd - 7.776) < near, format('custo %s ≠ 7,78', t.cost_usd);
  assert abs(t.profit_usd_as_is - (t.income_usd_as_is - 7.776)) < near, 'lucro com custo errado';
  update public.evaluation_settings set marginal = true;
  select * into t from public.evaluation_summary(7) where kind = 'total';
  assert t.cost_usd = 0, format('custo marginal %s ≠ 0', t.cost_usd);
  update public.evaluation_settings set marginal = false, kwh_price_brl = null;
  select * into t from public.evaluation_summary(7) where kind = 'total';
  assert t.cost_usd is null, 'tarifa vazia deveria dar custo desconhecido';

  -- caso 7: liquidez (20 dropados na semana contra 100 vendidos = 20%; contra 1.000 = 2%)
  select * into x from public.evaluation_liquidity(7) where name = 'Aval Pedra';
  assert abs(x.share - 0.20) < near and x.flagged, format('Pedra share %s', x.share);
  select * into x from public.evaluation_liquidity(7) where name = 'Aval Pena';
  assert abs(x.share - 0.02) < near and not x.flagged, format('Pena share %s', x.share);
end;
$$;

-- caso 6: o dono B não vê os parâmetros do dono A
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000e0b02', false);
do $$
begin
  assert not exists (select 1 from public.evaluation_settings), 'dono B viu os parâmetros do dono A';
  assert (select count(*) from public.evaluation_summary(7) where kind = 'account') = 1, 'dono B deveria ver 1 conta';
end;
$$;
reset role;

delete from public.events where account_id = '00000000-0000-0000-0000-00000e0ac001';
delete from public.market_prices where item_id in (910001, 910002);
delete from public.game_items where item_id in (910001, 910002);
delete from public.metric_hourly where account_id in
  ('00000000-0000-0000-0000-00000e0ac001', '00000000-0000-0000-0000-00000e0ac002',
   '00000000-0000-0000-0000-00000e0bc001');
delete from public.evaluation_settings where owner_id = '00000000-0000-0000-0000-0000000e0a01';
delete from public.accounts where nick in ('aval-1', 'aval-2', 'aval-b');
delete from auth.users where id in ('00000000-0000-0000-0000-0000000e0a01', '00000000-0000-0000-0000-0000000e0b02');
do $$ begin raise notice 'compensa: ok'; end $$;
