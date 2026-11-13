-- Teste da migration de ouro líquido. Não depende do simulador: cria a própria
-- conta e eventos numa hora de 2001 e apaga tudo no fim. Falha com exceção.
\set ON_ERROR_STOP 1

do $$
declare
  v_owner uuid;
  v_acc   uuid;
  v_hour  timestamptz := '2001-01-01 10:00+00';
  v_cons  numeric;
  v_net   numeric;
begin
  insert into auth.users default values returning id into v_owner;
  insert into public.accounts (owner_id, nick, role) values (v_owner, 'teste-ouro-liquido', 'farm')
    returning id into v_acc;

  insert into public.events (id, account_id, session_id, type, received_at, data) values
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_hour + interval '1 min',
     '{"gold": 41, "gold_autosell": 0, "xp": 11, "hunt_slug": "magikarp"}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'kill', v_hour + interval '2 min',
     '{"gold": 41, "gold_autosell": 0, "xp": 11, "hunt_slug": "magikarp"}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'capture_attempt', v_hour + interval '2 min',
     '{"ball_id": 2, "ball_price": 20, "success": false, "hunt_slug": "magikarp"}'),
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'capture_attempt', v_hour + interval '3 min',
     '{"ball_id": 1, "success": false, "hunt_slug": "magikarp"}'),  -- evento antigo, sem preço
    (gen_random_uuid(), v_acc, gen_random_uuid(), 'item.consumed', v_hour + interval '3 min',
     '{"item_id": 200, "qty": 2, "unit_price": 50, "hunt_slug": "magikarp"}');

  perform public.refresh_metric_hourly(v_hour, v_hour);

  select value into v_cons from public.metric_hourly
   where account_id = v_acc and metric = 'consumables_gold' and hunt_slug = 'magikarp';
  select value into v_net from public.metric_hourly
   where account_id = v_acc and metric = 'gold_net' and hunt_slug = 'magikarp';
  assert v_cons = 120, format('consumables_gold: %s ≠ 120', v_cons);  -- 20 + 2 × 50
  assert v_net = -38, format('gold_net: %s ≠ -38', v_net);            -- 82 − 120

  assert exists (select 1 from public.metric_definitions where key = 'gold_net_per_hour'),
    'gold_net_per_hour não definida';

  delete from public.metric_hourly where account_id = v_acc;
  delete from public.accounts where id = v_acc;
  delete from auth.users where id = v_owner;
  raise notice 'ouro líquido: ok';
end;
$$;
