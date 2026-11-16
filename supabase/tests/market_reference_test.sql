-- Teste do preço de referência (mediana das vendas). Cria os próprios dados e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values ('00000000-0000-0000-0000-0000000000a1');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000000ae01', '00000000-0000-0000-0000-0000000000a1', 'ref-dono', 'farm');
insert into public.game_items (item_id, name, source) values (990142, 'Teste Stone', 'json');

-- duas varreduras com a mesma venda 1 (conta uma vez); a 5 é a transferência de 5.000 gemas;
-- a 6 envolve a nossa conta
insert into public.events (id, account_id, session_id, type, received_at, data, raw)
select gen_random_uuid(), '00000000-0000-0000-0000-00000000ae01'::uuid, gen_random_uuid(), 'market.reply', now() - interval '1 hour',
       '{"aba": "historicoGlobal"}'::jsonb,
       jsonb_build_object('linhas', jsonb_build_array(
         jsonb_build_object('id', 1, 'em', extract(epoch from now()) * 1000, 'tipo', 'item', 'bruto', 20, 'moeda', 'orb',
                            'descricao', '10× Teste Stone', 'vendedor', 'a', 'comprador', 'b'),
         jsonb_build_object('id', 2, 'em', extract(epoch from now()) * 1000, 'tipo', 'item', 'bruto', 6, 'moeda', 'orb',
                            'descricao', '2× Teste Stone', 'vendedor', 'a', 'comprador', 'c'),
         jsonb_build_object('id', 3, 'em', extract(epoch from now()) * 1000, 'tipo', 'item', 'bruto', 2, 'moeda', 'orb',
                            'descricao', 'Teste Stone', 'vendedor', 'd', 'comprador', 'c'),
         jsonb_build_object('id', 4, 'em', extract(epoch from now()) * 1000, 'tipo', 'item', 'bruto', 40, 'moeda', 'orb',
                            'descricao', '20× Teste Stone', 'vendedor', 'e', 'comprador', 'c'),
         jsonb_build_object('id', 5, 'em', extract(epoch from now()) * 1000, 'tipo', 'item', 'bruto', 5000, 'moeda', 'orb',
                            'descricao', '1× Teste Stone', 'vendedor', 'x', 'comprador', 'y'),
         jsonb_build_object('id', 6, 'em', extract(epoch from now()) * 1000, 'tipo', 'item', 'bruto', 900, 'moeda', 'orb',
                            'descricao', '1× Teste Stone', 'vendedor', 'ref-dono', 'comprador', 'z'),
         jsonb_build_object('id', 7, 'em', extract(epoch from now()) * 1000, 'tipo', 'pokemon', 'bruto', 300, 'moeda', 'orb',
                            'descricao', 'Pikachu', 'vendedor', 'a', 'comprador', 'b')))
union all
select gen_random_uuid(), '00000000-0000-0000-0000-00000000ae01'::uuid, gen_random_uuid(), 'market.reply', now() - interval '30 minutes',
       '{"aba": "historicoGlobal"}'::jsonb,
       jsonb_build_object('linhas', jsonb_build_array(
         jsonb_build_object('id', 1, 'em', extract(epoch from now()) * 1000, 'tipo', 'item', 'bruto', 20, 'moeda', 'orb',
                            'descricao', '10× Teste Stone', 'vendedor', 'a', 'comprador', 'b')));

do $$
declare r record;
begin
  select * into r from public.market_reference() where item_name = 'Teste Stone';
  -- vendas 1–4 (unitários 2, 3, 2, 2; 33 unidades): mediana ponderada 2; a 5 é outlier; a 6 é nossa
  if r.sales <> 4 or r.units <> 33 or r.median_unit <> 2 or r.outliers <> 1 or r.own <> 1 or r.item_id <> 990142 then
    raise exception 'market_reference errado: %', row_to_json(r);
  end if;
  if r.raw_mean_unit < 100 then
    raise exception 'a média bruta deveria mostrar a distorção: %', r.raw_mean_unit;
  end if;
  raise notice 'market_reference: ok (%)', row_to_json(r);
end $$;

delete from public.events where account_id = '00000000-0000-0000-0000-00000000ae01';
delete from public.game_items where item_id = 990142;
delete from public.accounts where id = '00000000-0000-0000-0000-00000000ae01';
delete from auth.users where id = '00000000-0000-0000-0000-0000000000a1';
