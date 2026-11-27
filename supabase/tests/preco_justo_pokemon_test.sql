-- Teste do preço justo de pokémon (épico B). Cria os próprios dados e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values ('00000000-0000-0000-0000-0000000000b1');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000000be01', '00000000-0000-0000-0000-0000000000b1', 'pj-dono', 'farm');

-- Uma varredura do histórico global, gravada duas vezes (a venda conta uma vez). Espécie 990001, nível 100:
-- - vendas 1–6: potência 1, nota 3,0 a 3,5, preços 8, 9, 10, 10, 11, 12;
-- - venda 7: potência 1, 5.000 gemas (transferência, fora por ser > 3× a mediana);
-- - venda 8: potência 1, vendida por uma conta nossa (fora);
-- - venda 9: potência 5, 80 gemas (outra faixa);
-- - venda 10: shiny, 500 gemas (outro grupo);
-- - venda 11: item (não entra).
create temp table v (id int, pot int, nota numeric, preco numeric, shiny boolean, vendedor text, tipo text);
insert into v values
  (1, 1, 3.0, 8, false, 'a', 'pokemon'), (2, 1, 3.1, 9, false, 'a', 'pokemon'),
  (3, 1, 3.2, 10, false, 'a', 'pokemon'), (4, 1, 3.3, 10, false, 'a', 'pokemon'),
  (5, 1, 3.4, 11, false, 'a', 'pokemon'), (6, 1, 3.5, 12, false, 'a', 'pokemon'),
  (7, 1, 3.2, 5000, false, 'x', 'pokemon'), (8, 1, 3.2, 900, false, 'pj-dono', 'pokemon'),
  (9, 5, 3.2, 80, false, 'a', 'pokemon'), (10, 1, 3.2, 500, true, 'a', 'pokemon'),
  (11, 1, 3.2, 3, false, 'a', 'item');

insert into public.events (id, account_id, session_id, type, received_at, data, raw)
select gen_random_uuid(), '00000000-0000-0000-0000-00000000be01'::uuid, gen_random_uuid(), 'market.reply', now() - g * interval '1 minute',
       '{"aba": "historicoGlobal"}'::jsonb,
       jsonb_build_object('linhas', (select jsonb_agg(jsonb_build_object(
         'id', 990000 + v.id, 'em', extract(epoch from now() - interval '1 day') * 1000, 'tipo', v.tipo,
         'bruto', v.preco, 'moeda', 'orb', 'vendedor', v.vendedor, 'comprador', 'b',
         'ficha', case when v.tipo = 'pokemon' then jsonb_build_object(
           'speciesId', 990001, 'nome', 'Testemon', 'shiny', v.shiny, 'potencia', v.pot, 'nota', v.nota,
           'quality', 1.2, 'level', 100, 'poder', 300, 'ivTotal', 100, 'refinoTotal', 0, 'tmAoe', false,
           'tmElemental', null) end)) from v))
  from generate_series(1, 2) g;

do $$
declare r record; n int;
begin
  select count(*) into n from public.market_pokemon_sales where species_id = 990001;
  if n <> 10 then raise exception 'o gatilho deveria gravar 10 vendas de pokémon, gravou %', n; end if;
  if not (select is_own from public.market_pokemon_sales where sale_id = 990008) then
    raise exception 'a venda 8 é de uma conta nossa';
  end if;

  -- só 6 vendas comparáveis com potência 1: com mínimo 5, mesma potência
  select * into r from public.pokemon_fair_price(990001, false, 1, 3.25, 100);
  if r.sales <> 6 or r.outliers <> 1 or r.match <> 'exact' or r.confidence <> 'ok' then
    raise exception 'comparáveis errados: %', row_to_json(r);
  end if;
  if r.fair not between 9 and 11 or r.quick > r.fair or r.patient < r.fair then
    raise exception 'preços errados: %', row_to_json(r);
  end if;
  if r.fair_net <> public.pokemon_net_gems(r.fair) then
    raise exception 'líquido errado: %', row_to_json(r);
  end if;
  -- raridade: 8 vendas não shiny e não nossas (1–7 e 9); com nota >= 3,25 só a 4, a 5 e a 6
  if r.species_sales <> 8 or r.top_pct <> 37.5 then
    raise exception 'raridade errada: %', row_to_json(r);
  end if;

  -- nota alta puxa para as vendas de nota alta
  if (select fair from public.pokemon_fair_price(990001, false, 1, 3.5, 100))
     < (select fair from public.pokemon_fair_price(990001, false, 1, 3.0, 100)) then
    raise exception 'a nota não ajustou o preço';
  end if;

  -- potência 4 cai na faixa 4 (nenhuma venda): poucas referências
  select * into r from public.pokemon_fair_price(990001, false, 4, 3.2, 100);
  if r.confidence <> 'low' or r.sales <> 0 then raise exception 'P4 sem vendas: %', row_to_json(r); end if;

  -- potência 2 usa a faixa 1–3 porque não há vendas de P2
  select * into r from public.pokemon_fair_price(990001, false, 2, 3.2, 100);
  if r.match <> 'band' or r.sales <> 6 then raise exception 'faixa de potência: %', row_to_json(r); end if;

  -- nível 20 não compara com vendas de nível 100
  select * into r from public.pokemon_fair_price(990001, false, 1, 3.2, 20);
  if r.sales <> 0 then raise exception 'nível fora da faixa: %', row_to_json(r); end if;

  -- shiny: uma venda só
  select * into r from public.pokemon_fair_price(990001, true, 1, 3.2, 100);
  if r.confidence <> 'low' or r.sales <> 1 then raise exception 'shiny: %', row_to_json(r); end if;

  if public.pokemon_price_verdict(5, 10, 'ok') <> 'excepcional'
     or public.pokemon_price_verdict(7, 10, 'ok') <> 'ótimo'
     or public.pokemon_price_verdict(9, 10, 'ok') <> 'bom'
     or public.pokemon_price_verdict(11, 10, 'ok') <> 'justo'
     or public.pokemon_price_verdict(20, 10, 'ok') <> 'caro'
     or public.pokemon_price_verdict(5, 10, 'low') <> 'poucas referências' then
    raise exception 'veredito errado';
  end if;
  if public.pokemon_net_gems(2000) <> 1785 then raise exception 'comissão errada'; end if;
  raise notice 'pokemon_fair_price: ok';
end $$;

-- a coleção e a vitrine
insert into public.account_pokemon (account_id, pokemon_id, species_id, data) values
  ('00000000-0000-0000-0000-00000000be01', 1, 990001, '{"shiny": false, "potency": 1, "grade": 3.3, "level": 100}'),
  ('00000000-0000-0000-0000-00000000be01', 2, 990002, '{"shiny": false, "potency": 1, "grade": 3.3, "level": 100}');

insert into public.events (id, account_id, session_id, type, received_at, data, raw)
values (gen_random_uuid(), '00000000-0000-0000-0000-00000000be01', gen_random_uuid(), 'market.reply', now(),
        '{"aba": "vitrine"}',
        jsonb_build_object('linhas', jsonb_build_array(
          jsonb_build_object('id', 1, 'tipo', 'pokemon', 'moeda', 'orb', 'preco', 5, 'vendedor', 'z',
            'ficha', jsonb_build_object('speciesId', 990001, 'nome', 'Testemon', 'shiny', false, 'potencia', 1,
                                        'nota', 3.2, 'level', 100)),
          jsonb_build_object('id', 2, 'tipo', 'pokemon', 'moeda', 'orb', 'preco', 50, 'vendedor', 'pj-dono',
            'ficha', jsonb_build_object('speciesId', 990001, 'nome', 'Testemon', 'shiny', false, 'potencia', 1,
                                        'nota', 3.2, 'level', 100)))));

do $$
declare r record; n int;
begin
  select count(*) into n from public.pokemon_prices('00000000-0000-0000-0000-00000000be01');
  if n <> 1 then raise exception 'pokemon_prices deveria trazer só o 990001 (o outro não tem venda): %', n; end if;
  select * into r from public.pokemon_prices('00000000-0000-0000-0000-00000000be01');
  if r.pokemon_id <> 1 or r.confidence <> 'ok' then raise exception 'pokemon_prices: %', row_to_json(r); end if;

  select count(*) into n from public.pokemon_listing_verdicts();
  if n <> 1 then raise exception 'a vitrine deveria trazer 1 anúncio (o nosso fica fora): %', n; end if;
  select * into r from public.pokemon_listing_verdicts();
  if r.verdict <> 'excepcional' or r.diff_pct >= -40 then raise exception 'vitrine: %', row_to_json(r); end if;
  raise notice 'pokemon_prices e vitrine: ok';
end $$;

delete from public.account_pokemon where account_id = '00000000-0000-0000-0000-00000000be01';
delete from public.events where account_id = '00000000-0000-0000-0000-00000000be01';
delete from public.market_pokemon_sales where species_id = 990001;
delete from public.accounts where id = '00000000-0000-0000-0000-00000000be01';
delete from auth.users where id = '00000000-0000-0000-0000-0000000000b1';
