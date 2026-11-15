-- Teste do valor dos drops (fase 7; docs/design/fase-7-precos-do-mercado.md, casos 6 a 9).
-- Cria a própria conta, itens, preços e eventos em 2001 e apaga tudo no fim.
\set ON_ERROR_STOP 1

do $$
declare
  v_owner uuid;
  v_acc   uuid;
  v_h1    timestamptz := '2001-01-01 10:00+00';  -- antes de qualquer snapshot
  v_h2    timestamptz := '2001-01-01 12:00+00';
  v       numeric;
begin
  insert into auth.users default values returning id into v_owner;
  insert into public.accounts (owner_id, nick, role) values (v_owner, 'teste-drops-valor', 'farm')
    returning id into v_acc;

  insert into public.game_items (item_id, name, category, rare, npc_price, source) values
    (900001, 'Pedra Teste', 'stone', true, 5000, 'json'),
    (900002, 'Pena Teste', 'loot', false, 300, 'json');

  -- para a hora das 12 vale o último snapshot antes das 13:00 (o das 12:30); o das 13:10 não
  insert into public.market_prices (taken_at, item_id, currency, avg, units, days) values
    ('2001-01-01 11:30+00', 900001, 'orb', 99, 1, 7),
    ('2001-01-01 12:30+00', 900001, 'orb', 12.5, 340, 7),
    ('2001-01-01 12:30+00', 900001, 'gold', 4800, 90, 7),
    ('2001-01-01 13:10+00', 900001, 'orb', 1000, 1, 7);  -- depois da hora: não conta

  insert into public.events (id, account_id, session_id, type, received_at, data) values
    -- hora 10: antes de qualquer snapshot -> só npc_price em ouro
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_h1 + interval '1 min',
     '{"hunt_slug": "x", "drops": [{"name": "Pedra Teste", "qty": 2}]}'),
    -- hora 12: 3 + 1 Pedra Teste (caso 6: 4 unidades), 2 Pena Teste sem média, 1 desconhecido
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_h2 + interval '1 min',
     '{"hunt_slug": "x", "drops": [{"name": "Pedra Teste", "qty": 3}]}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_h2 + interval '2 min',
     '{"hunt_slug": "x", "drops": [{"name": "Pedra Teste"}, {"name": "Pena Teste", "qty": 2}]}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_h2 + interval '3 min',
     '{"hunt_slug": "x", "drops": [{"name": "Coisa Nova", "qty": 1}]}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_h2 + interval '4 min',
     '{"hunt_slug": "x", "drops": []}');

  perform public.refresh_metric_hourly(v_h1, v_h2);

  -- caso 6: unidades (4 Pedra + 2 Pena + 1 desconhecido = 7 na hora 12)
  select value into v from public.metric_hourly
   where account_id = v_acc and hour = v_h2 and metric = 'drops';
  assert v = 7, format('drops hora 12: %s ≠ 7', v);

  -- caso 7: 4 Pedra × 12,5 (snapshot das 12:30, não o das 13:10) = 50 gemas
  select value into v from public.metric_hourly
   where account_id = v_acc and hour = v_h2 and metric = 'drops_value_orb';
  assert v = 50, format('drops_value_orb hora 12: %s ≠ 50', v);

  -- caso 8: ouro = 4 × 4800 + 2 Pena pelo npc_price (2 × 300) = 19.800; desconhecido = 0
  select value into v from public.metric_hourly
   where account_id = v_acc and hour = v_h2 and metric = 'drops_value_gold';
  assert v = 19800, format('drops_value_gold hora 12: %s ≠ 19800', v);
  select value into v from public.metric_hourly
   where account_id = v_acc and hour = v_h2 and metric = 'drops_unpriced';
  assert v = 1, format('drops_unpriced hora 12: %s ≠ 1', v);

  -- caso 8: antes de qualquer snapshot, só o npc_price em ouro (2 × 5000), gemas 0
  select value into v from public.metric_hourly
   where account_id = v_acc and hour = v_h1 and metric = 'drops_value_gold';
  assert v = 10000, format('drops_value_gold hora 10: %s ≠ 10000', v);
  assert not exists (select 1 from public.metric_hourly
                      where account_id = v_acc and hour = v_h1 and metric = 'drops_value_orb'),
    'drops_value_orb na hora 10 deveria ser 0 (sem linha)';

  -- caso 9: retenção
  insert into public.market_prices (taken_at, item_id, currency, avg) values
    (now() - interval '31 days', 900001, 'orb', 1);
  assert public.purge_market_prices() >= 1, 'purge_market_prices não apagou';
  assert not exists (select 1 from public.market_prices where taken_at < now() - interval '30 days'),
    'sobrou snapshot com mais de 30 dias';

  delete from public.metric_hourly where account_id = v_acc;
  delete from public.market_prices where item_id in (900001, 900002);
  delete from public.game_items where item_id in (900001, 900002);
  delete from public.accounts where id = v_acc;
  delete from auth.users where id = v_owner;
  raise notice 'valor dos drops: ok';
end;
$$;
