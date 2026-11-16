-- Perfil da conta para o painel (docs/design/painel-perfil.md).
--
-- Uma linha por conta, gravada pelo plugin `profile` do worker a cada ~2 min: o `estado` do jogo
-- (welcome + patches) resumido em números, equipe, destaques da coleção e inventário. O painel lê
-- daqui em vez de remontar o estado a partir dos eventos.
--
-- E o ícone dos itens (`icon` do items.json e do itensNossos do welcome), para o painel mostrar
-- a imagem do jogo.

create table public.account_profile (
  account_id         uuid primary key references public.accounts (id) on delete cascade,
  updated_at         timestamptz not null default now(),
  level              int,
  xp                 numeric,
  xp_level           numeric,          -- estado.xpNivel
  xp_next            numeric,          -- estado.xpProximo
  gold               numeric,
  gems               numeric,          -- estado.orbs
  diamonds           numeric,
  vip_until          timestamptz,      -- estado.loja.vipAte
  hunt_slug          text,
  active_pokemon_id  bigint,
  pokemon_count      int not null default 0,
  shiny_count        int not null default 0,
  dex_seen           int not null default 0,
  dex_caught         int not null default 0,
  team               jsonb not null default '[]'::jsonb,
  top_pokemon        jsonb not null default '[]'::jsonb,
  shinies            jsonb not null default '[]'::jsonb,
  items              jsonb not null default '{}'::jsonb,
  balls              jsonb not null default '{}'::jsonb,
  estado_keys        jsonb not null default '[]'::jsonb  -- só os nomes dos campos do estado
);

alter table public.account_profile enable row level security;
create policy own_account_profile on public.account_profile
  for select to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())));
-- escrita: só a service_role (worker), que ignora RLS

alter table public.game_items add column icon text;

create or replace function public.replace_game_items(p_source text, p_version text, p_rows jsonb, p_meta jsonb)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.game_items
   where source = p_source
     and item_id not in (select (r->>'item_id')::bigint from jsonb_array_elements(p_rows) r);

  insert into public.game_items (item_id, name, category, rare, npc_price, icon, source, updated_at)
  select (r->>'item_id')::bigint, r->>'name', r->>'category', coalesce((r->>'rare')::boolean, false),
         (r->>'npc_price')::numeric, nullif(r->>'icon', ''), p_source, now()
    from jsonb_array_elements(p_rows) r
  on conflict (item_id) do update
     set name = excluded.name, category = excluded.category, rare = excluded.rare,
         npc_price = coalesce(excluded.npc_price, public.game_items.npc_price),
         icon = coalesce(excluded.icon, public.game_items.icon),
         source = excluded.source, updated_at = now();

  insert into public.game_catalog (key, version, data, updated_at)
  values ('items_' || p_source, p_version, p_meta, now())
  on conflict (key) do update
     set version = excluded.version, data = excluded.data, updated_at = now();
end;
$$;

revoke all on function public.replace_game_items(text, text, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.replace_game_items(text, text, jsonb, jsonb) to service_role;
