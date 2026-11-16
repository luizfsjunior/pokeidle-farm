-- Teste da migration do perfil da conta e do ícone dos itens. Cria os próprios dados e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values
  ('00000000-0000-0000-0000-0000000000a1'), ('00000000-0000-0000-0000-0000000000b2');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000000af01', '00000000-0000-0000-0000-0000000000a1', 'perfil-dono', 'farm'),
  ('00000000-0000-0000-0000-00000000af02', '00000000-0000-0000-0000-0000000000b2', 'perfil-outro', 'farm');

-- o worker (service_role ignora RLS; aqui, o dono do banco) grava as duas
insert into public.account_profile (account_id, level, gold, gems, team) values
  ('00000000-0000-0000-0000-00000000af01', 38, 41000, 12, '[{"name": "Kabuto", "slot": 0}]'),
  ('00000000-0000-0000-0000-00000000af02', 10, 5, 0, '[]');
insert into public.account_profile (account_id, level, gold) values
  ('00000000-0000-0000-0000-00000000af01', 39, 42000)
  on conflict (account_id) do update set level = excluded.level, gold = excluded.gold;

-- histórico diário: a trigger guarda a última gravação de cada dia
do $$
begin
  if (select gold from public.account_profile_daily
       where account_id = '00000000-0000-0000-0000-00000000af01') <> 42000 then
    raise exception 'account_profile_daily não acompanhou o upsert';
  end if;
  update public.account_profile set updated_at = now() - interval '2 days', gold = 1
   where account_id = '00000000-0000-0000-0000-00000000af01';
  if (select count(*) from public.account_profile_daily
       where account_id = '00000000-0000-0000-0000-00000000af01') <> 2 then
    raise exception 'dia anterior não virou outra linha';
  end if;
end $$;

-- ícone: o items.json traz, o welcome sem ícone não apaga
select public.replace_game_items('json', 'v1',
  '[{"item_id": 990001, "name": "Teste Stone", "icon": "items/teste.png"}]', '{}');
select public.replace_game_items('welcome', 'v1', '[{"item_id": 990001, "name": "Teste Stone"}]', '{}');

do $$
begin
  if (select icon from public.game_items where item_id = 990001) is distinct from 'items/teste.png' then
    raise exception 'ícone do item se perdeu';
  end if;
end $$;

-- Como o dono, pelo painel: vê só a própria conta e não escreve
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000000a1', false);

do $$
begin
  if (select count(*) from public.account_profile) <> 1 then
    raise exception 'RLS: o dono enxerga perfil alheio';
  end if;
  if (select level from public.account_profile) <> 39 then
    raise exception 'upsert não atualizou o perfil';
  end if;
  if (select count(distinct account_id) from public.account_profile_daily) <> 1 then
    raise exception 'RLS: o dono enxerga histórico alheio';
  end if;
  begin
    update public.account_profile set gold = 0;
    if exists (select 1 from public.account_profile where gold = 0) then
      raise exception 'painel conseguiu alterar o perfil';
    end if;
  exception when insufficient_privilege then null;
  end;
end $$;

reset role;
delete from public.game_items where item_id = 990001;
delete from public.accounts where id in
  ('00000000-0000-0000-0000-00000000af01', '00000000-0000-0000-0000-00000000af02');
delete from auth.users where id in
  ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-0000000000b2');
select 'account_profile_test ok';
