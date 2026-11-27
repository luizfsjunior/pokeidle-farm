-- Teste de market_sales_events() e da retenção da aba `item` (20261127150000). Cria os próprios dados e
-- apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values
  ('00000000-0000-0000-0000-0000000005a1'), ('00000000-0000-0000-0000-0000000005b2');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000000c501', '00000000-0000-0000-0000-0000000005a1', 'vendas-a1', 'farm'),
  ('00000000-0000-0000-0000-00000000c502', '00000000-0000-0000-0000-0000000005a1', 'vendas-a2', 'farm'),
  ('00000000-0000-0000-0000-00000000c503', '00000000-0000-0000-0000-0000000005b2', 'vendas-b', 'farm');

insert into public.events (id, account_id, session_id, type, received_at, data, raw)
select gen_random_uuid(), acc, gen_random_uuid(), t, now() - age, d::jsonb, coalesce(r, '{}')::jsonb
  from (values
    -- conta a1: uma de cada fonte, mais as que não entram
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'market.reply', interval '1 hour', '{"aba": "meus"}', '{"linhas": []}'),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'action.sent', interval '1 hour', '{"action": "market.criar"}', '{"x": 1}'),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'seller.plan', interval '1 hour', '{"stones": []}', null),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'unknown', interval '1 hour', '{"t": "venda"}', '{"t": "venda"}'),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'action.sent', interval '1 hour', '{"action": "hunt.trocar"}', null),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'market.reply', interval '1 hour', '{"aba": "item"}', '{"linhas": []}'),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'unknown', interval '1 hour', '{"t": "outro"}', null),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'action.sent', interval '40 days', '{"action": "market.criar"}', null),
    -- conta a2 (mesmo dono) e b (outro dono)
    ('00000000-0000-0000-0000-00000000c502'::uuid, 'action.failed', interval '2 hours', '{"action": "market.cancelar"}', null),
    ('00000000-0000-0000-0000-00000000c503'::uuid, 'action.sent', interval '1 hour', '{"action": "market.criar"}', null),
    -- retenção: a aba item com 3 dias sai; a vitrine e o historicoGlobal com 3 dias ficam
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'market.reply', interval '3 days', '{"aba": "item"}', '{"linhas": []}'),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'market.reply', interval '3 days', '{"aba": "vitrine"}', '{"linhas": []}'),
    ('00000000-0000-0000-0000-00000000c501'::uuid, 'market.reply', interval '3 days', '{"aba": "historicoGlobal"}', '{"linhas": []}')
  ) v(acc, t, age, d, r);

select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000005a1', false);
set role authenticated;
do $$
declare n int; n_a1 int; n_raw int; n_b int;
begin
  select count(*), count(*) filter (where x->>'account_id' = '00000000-0000-0000-0000-00000000c501'),
         count(*) filter (where jsonb_typeof(x->'raw') = 'object'),
         count(*) filter (where x->>'account_id' = '00000000-0000-0000-0000-00000000c503')
    into n, n_a1, n_raw, n_b
    from jsonb_array_elements(public.market_sales_events(now() - interval '30 days')) x;
  -- a1: meus, market.criar, seller.plan, venda (e não hunt.trocar, aba item, t outro, nem o de 40 dias); a2: cancelar
  if n <> 5 or n_a1 <> 4 or n_b <> 0 then
    raise exception 'market_sales_events errado: % linhas, % da a1, % da conta de outro dono', n, n_a1, n_b;
  end if;
  -- o raw só vem das respostas do Mercado e dos avisos
  if n_raw <> 2 then raise exception 'raw em % linhas (esperava 2)', n_raw; end if;

  select jsonb_array_length(public.market_sales_events(now() - interval '30 days', '00000000-0000-0000-0000-00000000c502')) into n;
  if n <> 1 then raise exception 'filtro por conta: % linhas', n; end if;
  -- conta de outro dono pedida pelo id: nada
  select jsonb_array_length(public.market_sales_events(now() - interval '30 days', '00000000-0000-0000-0000-00000000c503')) into n;
  if n <> 0 then raise exception 'leu conta de outro dono: % linhas', n; end if;
  raise notice 'market_sales_events: ok';
end $$;
reset role;

-- sem login não roda
do $$
begin
  set local role anon;
  perform public.market_sales_events(now());
  raise exception 'anon conseguiu chamar market_sales_events';
exception when insufficient_privilege then
  raise notice 'market_sales_events sem login: bloqueado, ok';
end $$;

select public.prune_events();
do $$
declare n_item int; n_kept int;
begin
  select count(*) filter (where data->>'aba' = 'item' and received_at < now() - interval '2 days'),
         count(*) filter (where data->>'aba' in ('vitrine', 'historicoGlobal'))
    into n_item, n_kept
    from public.events where account_id = '00000000-0000-0000-0000-00000000c501' and type = 'market.reply';
  if n_item <> 0 or n_kept <> 2 then raise exception 'retenção da aba item: % velhas, % mantidas', n_item, n_kept; end if;
  raise notice 'retenção da aba item: ok';
end $$;

delete from public.events where account_id in ('00000000-0000-0000-0000-00000000c501', '00000000-0000-0000-0000-00000000c502',
                                              '00000000-0000-0000-0000-00000000c503');
delete from public.accounts where owner_id in ('00000000-0000-0000-0000-0000000005a1', '00000000-0000-0000-0000-0000000005b2');
delete from auth.users where id in ('00000000-0000-0000-0000-0000000005a1', '00000000-0000-0000-0000-0000000005b2');
