-- Fase 4b: comandos do painel para o worker (docs/design/fase-4b-comandos.md).
--
-- O painel insere em `commands` (só para contas próprias, sempre `pending`).
-- O worker (service_role) pega com claim_commands, executa e fecha com
-- finish_command. Cancelar um pendente: cancel_command(id).

create table public.commands (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  account_id   uuid not null references public.accounts (id) on delete cascade,
  type         text not null check (type in (
                 'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set')),
  params       jsonb not null default '{}'::jsonb,
  status       text not null default 'pending'
               check (status in ('pending', 'running', 'done', 'failed', 'cancelled', 'expired')),
  result       jsonb,
  error        text,
  holder       text,
  created_at   timestamptz not null default now(),
  started_at   timestamptz,
  finished_at  timestamptz,
  expires_at   timestamptz not null default now() + interval '5 minutes'
);
create index commands_account_status on public.commands (account_id, status, created_at);
create index commands_owner_created  on public.commands (owner_id, created_at desc);

alter table public.commands enable row level security;

create policy own_commands_select on public.commands
  for select to authenticated
  using (owner_id = (select auth.uid()));

-- O painel só cria pendentes, para contas próprias, sem preencher o que é do worker.
create policy own_commands_insert on public.commands
  for insert to authenticated
  with check (
    owner_id = (select auth.uid())
    and account_id in (select id from public.accounts where owner_id = (select auth.uid()))
    and status = 'pending'
    and result is null and error is null and holder is null
    and started_at is null and finished_at is null
    and expires_at <= now() + interval '1 hour'
  );

-- Sem policy de update/delete: mudanças de status só pelas funções abaixo.

-- ---------------------------------------------------------------------------
-- Funções
-- ---------------------------------------------------------------------------

-- Cancela um comando próprio que ainda não foi pego.
create function public.cancel_command(p_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.commands
     set status = 'cancelled', finished_at = now()
   where id = p_id and status = 'pending' and owner_id = auth.uid();
  return found;
end;
$$;

-- Pega os pendentes das contas informadas (atômico: dois workers nunca pegam o
-- mesmo). Antes, marca como expirados os que passaram do prazo.
create function public.claim_commands(p_holder text, p_accounts uuid[], p_limit int default 20)
returns setof public.commands
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.commands
     set status = 'expired', finished_at = now()
   where status = 'pending' and expires_at < now() and account_id = any (p_accounts);

  return query
  update public.commands c
     set status = 'running', started_at = now(), holder = p_holder
    from (select id from public.commands
           where status = 'pending' and account_id = any (p_accounts)
           order by created_at
           limit p_limit
           for update skip locked) pick
   where c.id = pick.id
  returning c.*;
end;
$$;

-- Fecha um comando que está rodando.
create function public.finish_command(p_id uuid, p_status text, p_result jsonb default null, p_error text default null)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_status not in ('done', 'failed') then
    raise exception 'status final deve ser done ou failed';
  end if;
  update public.commands
     set status = p_status, result = p_result, error = left(p_error, 500), finished_at = now()
   where id = p_id and status = 'running';
  return found;
end;
$$;

-- Ao subir, o worker marca como falhos os comandos que ele pegou e não fechou
-- (morreu no meio). Não reexecuta: o efeito pode já ter acontecido.
create function public.recover_commands(p_holder text)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v int;
begin
  update public.commands
     set status = 'failed', error = 'interrompido (o worker reiniciou)', finished_at = now()
   where status = 'running' and holder = p_holder;
  get diagnostics v = row_count;
  return v;
end;
$$;

create function public.purge_commands()
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
  v int;
begin
  delete from public.commands
   where status not in ('pending', 'running') and created_at < now() - interval '30 days';
  get diagnostics v = row_count;
  return v;
end;
$$;

revoke all on function public.cancel_command(uuid)                  from public, anon;
revoke all on function public.claim_commands(text, uuid[], int)     from public, anon, authenticated;
revoke all on function public.finish_command(uuid, text, jsonb, text) from public, anon, authenticated;
revoke all on function public.recover_commands(text)                from public, anon, authenticated;
revoke all on function public.purge_commands()                      from public, anon, authenticated;
grant execute on function public.cancel_command(uuid)                  to authenticated;
grant execute on function public.claim_commands(text, uuid[], int)     to service_role;
grant execute on function public.finish_command(uuid, text, jsonb, text) to service_role;
grant execute on function public.recover_commands(text)                to service_role;
grant execute on function public.purge_commands()                      to service_role;

-- ---------------------------------------------------------------------------
-- Realtime (o painel pode assinar as mudanças) e retenção
-- ---------------------------------------------------------------------------

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.commands;
  end if;
  if exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    create extension if not exists pg_cron with schema pg_catalog;
    perform cron.schedule('commands-purge', '23 4 * * *', 'select public.purge_commands()');
  end if;
end;
$$;
