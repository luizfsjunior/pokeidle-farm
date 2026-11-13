-- Teste da migration de comandos (fase 4b). Cria os próprios dados e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values
  ('00000000-0000-0000-0000-0000000000a1'), ('00000000-0000-0000-0000-0000000000b2');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000000ac01', '00000000-0000-0000-0000-0000000000a1', 'cmd-dono', 'farm'),
  ('00000000-0000-0000-0000-00000000ac02', '00000000-0000-0000-0000-0000000000b2', 'cmd-outro', 'farm');

-- Como o dono, pelo painel
set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000000a1', false);

insert into public.commands (account_id, type) values
  ('00000000-0000-0000-0000-00000000ac01', 'ping'),
  ('00000000-0000-0000-0000-00000000ac01', 'session.reconnect'),
  ('00000000-0000-0000-0000-00000000ac01', 'account.disable');

do $$
begin
  -- conta de outro usuário
  begin
    insert into public.commands (account_id, type) values ('00000000-0000-0000-0000-00000000ac02', 'ping');
    raise exception 'criou comando para conta alheia';
  exception when insufficient_privilege then null;
  end;
  -- não pode nascer como running nem com resultado
  begin
    insert into public.commands (account_id, type, status) values ('00000000-0000-0000-0000-00000000ac01', 'ping', 'running');
    raise exception 'criou comando já running';
  exception when insufficient_privilege then null;
  end;
  -- tipo desconhecido
  begin
    insert into public.commands (account_id, type) values ('00000000-0000-0000-0000-00000000ac01', 'rm -rf');
    raise exception 'aceitou tipo desconhecido';
  exception when check_violation then null;
  end;
  -- sem update direto
  update public.commands set status = 'done';
  assert not exists (select 1 from public.commands where status = 'done'), 'update direto passou';
  -- não chama as funções do worker
  begin
    perform public.claim_commands('x', array['00000000-0000-0000-0000-00000000ac01'::uuid]);
    raise exception 'authenticated chamou claim_commands';
  exception when insufficient_privilege then null;
  end;
  assert (select count(*) from public.commands) = 3, 'dono deveria ver 3 comandos';
  -- cancela o último pendente
  assert public.cancel_command((select id from public.commands where type = 'account.disable')), 'cancel falhou';
end;
$$;

-- O outro usuário não vê nem cancela
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000000b2', false);
do $$
begin
  assert (select count(*) from public.commands) = 0, 'outro usuário vê comandos alheios';
end;
$$;
reset role;

do $$
declare
  v_ping uuid;
  n int;
begin
  assert not public.cancel_command((select id from public.commands where type = 'ping')), 'cancel sem dono passou';

  -- claim atômico e em ordem; o cancelado não vem
  select count(*) into n from public.claim_commands('pc-casa', array['00000000-0000-0000-0000-00000000ac01'::uuid], 1);
  assert n = 1, 'limit 1 deveria pegar 1';
  select id into v_ping from public.commands where status = 'running';
  assert (select type from public.commands where id = v_ping) = 'ping', 'não pegou o mais antigo';
  select count(*) into n from public.claim_commands('pc-casa', array['00000000-0000-0000-0000-00000000ac01'::uuid]);
  assert n = 1, 'segundo claim deveria pegar só o reconnect';
  select count(*) into n from public.claim_commands('pc-casa', array['00000000-0000-0000-0000-00000000ac01'::uuid]);
  assert n = 0, 'nada mais pendente';
  -- conta não listada não é pega
  insert into public.commands (owner_id, account_id, type) values
    ('00000000-0000-0000-0000-0000000000b2', '00000000-0000-0000-0000-00000000ac02', 'ping');
  select count(*) into n from public.claim_commands('pc-casa', array['00000000-0000-0000-0000-00000000ac01'::uuid]);
  assert n = 0, 'pegou comando de conta não listada';

  -- finish
  assert public.finish_command(v_ping, 'done', '{"state": "ready"}'), 'finish falhou';
  assert not public.finish_command(v_ping, 'failed'), 'finish duas vezes passou';
  begin
    perform public.finish_command(v_ping, 'pending');
    raise exception 'aceitou status final inválido';
  exception when raise_exception then null;
  end;

  -- recover: o reconnect ficou running com o holder
  assert public.recover_commands('outro-pc') = 0, 'recover de outro holder mexeu';
  assert public.recover_commands('pc-casa') = 1, 'recover deveria marcar 1';
  assert (select status from public.commands where type = 'session.reconnect') = 'failed', 'recover não marcou failed';

  -- expiração
  insert into public.commands (owner_id, account_id, type, expires_at) values
    ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-00000000ac01', 'ping', now() - interval '1 second');
  select count(*) into n from public.claim_commands('pc-casa', array['00000000-0000-0000-0000-00000000ac01'::uuid]);
  assert n = 0, 'pegou comando expirado';
  assert exists (select 1 from public.commands where status = 'expired'), 'não marcou expirado';

  -- retenção
  update public.commands set created_at = now() - interval '31 days' where status = 'done';
  assert public.purge_commands() = 1, 'purge deveria apagar 1';

  delete from public.accounts where nick in ('cmd-dono', 'cmd-outro');
  delete from auth.users where id in ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-0000000000b2');
  raise notice 'comandos: ok';
end;
$$;
