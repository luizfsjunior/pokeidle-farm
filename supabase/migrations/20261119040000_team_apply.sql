-- Montar a equipe no painel e aplicar numa ida só ao Pokécenter (docs/design/conta-v2.md, seção 3).
-- team_drafts guarda o rascunho (uma linha por conta, sem histórico); team.apply é o comando.

create table public.team_drafts (
  account_id  uuid primary key references public.accounts (id) on delete cascade,
  team        bigint[] not null default '{}',   -- ids por vaga, da 1 à 5 (null = vaga vazia)
  active_id   bigint,
  updated_at  timestamptz not null default now()
);

alter table public.team_drafts enable row level security;
create policy own_team_drafts on public.team_drafts
  for all to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())))
  with check (account_id in (select id from public.accounts where owner_id = (select auth.uid())));

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move',
  'center.heal', 'team.apply'));
