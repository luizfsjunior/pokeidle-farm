-- 0001 — schema inicial (fase 2). Ver docs/design/fase-2.md, seção 4.
--
-- Tokens ficam no Supabase Vault; nenhuma tabela guarda token em texto.
-- Leitura e escrita de token e lease só pela service_role (o worker).
--
-- Cadastro de conta (pelo SQL editor, até existir o painel):
--   insert into public.accounts (owner_id, nick, role)
--   values ('<seu auth.users.id>', '<nick>', 'farm');
-- Depois grave o token com: pokeidle-farm set-token --nick <nick> --device <id-dispositivo>

-- ---------------------------------------------------------------------------
-- Tabelas
-- ---------------------------------------------------------------------------

create table public.accounts (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users (id) on delete cascade,
  nick        text not null unique,
  role        text not null check (role in ('farm', 'personal')),
  enabled     boolean not null default true,
  status      text not null default 'offline'
              check (status in ('offline', 'connecting', 'ready', 'needs_login', 'rejected')),
  created_at  timestamptz not null default now()
);

-- Referência ao segredo no Vault + dispositivo da conta.
create table public.account_tokens (
  account_id      uuid primary key references public.accounts (id) on delete cascade,
  token_secret_id uuid not null,
  device_id       text not null,
  renewed_at      timestamptz not null default now()
);

-- Só uma instância do worker por conta ao mesmo tempo (o mesmo token em dois
-- lugares derruba um deles com close 4001).
create table public.account_leases (
  account_id  uuid primary key references public.accounts (id) on delete cascade,
  holder      text not null,
  expires_at  timestamptz not null
);

-- Eventos brutos e imutáveis: a fonte da verdade das métricas.
create table public.events (
  id          uuid primary key,
  account_id  uuid not null references public.accounts (id) on delete cascade,
  session_id  uuid not null,
  type        text not null,
  server_ts   timestamptz,
  received_at timestamptz not null,
  data        jsonb not null default '{}'::jsonb,
  raw         jsonb not null default '{}'::jsonb
);
create index events_account_time on public.events (account_id, received_at desc);
create index events_type_time    on public.events (type, received_at desc);

create table public.strategy_configs (
  account_id  uuid not null references public.accounts (id) on delete cascade,
  plugin      text not null,
  enabled     boolean not null default false,
  config      jsonb not null default '{}'::jsonb,
  updated_at  timestamptz not null default now(),
  primary key (account_id, plugin)
);

-- ---------------------------------------------------------------------------
-- RLS: o dono vê as próprias contas, eventos e configs.
-- account_tokens e account_leases sem policy: só a service_role acessa.
-- ---------------------------------------------------------------------------

alter table public.accounts         enable row level security;
alter table public.account_tokens   enable row level security;
alter table public.account_leases   enable row level security;
alter table public.events           enable row level security;
alter table public.strategy_configs enable row level security;

create policy own_accounts on public.accounts
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));

create policy own_events on public.events
  for select to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())));

create policy own_configs on public.strategy_configs
  for all to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())))
  with check (account_id in (select id from public.accounts where owner_id = (select auth.uid())));

-- ---------------------------------------------------------------------------
-- Token no Vault
-- ---------------------------------------------------------------------------

create function public.set_account_token(p_account uuid, p_token text, p_device text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_secret uuid;
begin
  select token_secret_id into v_secret
    from public.account_tokens
   where account_id = p_account;

  if v_secret is null then
    v_secret := vault.create_secret(
      p_token,
      'pokeidle_token_' || p_account::text,
      'Token de sessão do pokeidle.io'
    );
    insert into public.account_tokens (account_id, token_secret_id, device_id)
    values (p_account, v_secret, p_device);
  else
    perform vault.update_secret(v_secret, p_token);
    update public.account_tokens
       set device_id = coalesce(nullif(p_device, ''), device_id),
           renewed_at = now()
     where account_id = p_account;
  end if;
end;
$$;

create function public.get_account_token(p_account uuid)
returns table (token text, device_id text)
language sql
security definer
set search_path = ''
as $$
  select s.decrypted_secret, t.device_id
    from public.account_tokens t
    join vault.decrypted_secrets s on s.id = t.token_secret_id
   where t.account_id = p_account;
$$;

-- ---------------------------------------------------------------------------
-- Lease
-- ---------------------------------------------------------------------------

-- Pega ou renova o lease. Retorna false se outra instância tem um lease válido.
create function public.acquire_account_lease(p_account uuid, p_holder text, p_ttl_seconds int)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.account_leases as l (account_id, holder, expires_at)
  values (p_account, p_holder, now() + make_interval(secs => p_ttl_seconds))
  on conflict (account_id) do update
     set holder = excluded.holder,
         expires_at = excluded.expires_at
   where l.holder = excluded.holder
      or l.expires_at < now();
  return found;
end;
$$;

create function public.release_account_lease(p_account uuid, p_holder text)
returns void
language sql
security definer
set search_path = ''
as $$
  delete from public.account_leases where account_id = p_account and holder = p_holder;
$$;

-- Só a service_role (worker) executa as funções sensíveis.
revoke all on function public.set_account_token(uuid, text, text)       from public, anon, authenticated;
revoke all on function public.get_account_token(uuid)                   from public, anon, authenticated;
revoke all on function public.acquire_account_lease(uuid, text, int)    from public, anon, authenticated;
revoke all on function public.release_account_lease(uuid, text)         from public, anon, authenticated;
grant execute on function public.set_account_token(uuid, text, text)    to service_role;
grant execute on function public.get_account_token(uuid)                to service_role;
grant execute on function public.acquire_account_lease(uuid, text, int) to service_role;
grant execute on function public.release_account_lease(uuid, text)      to service_role;
