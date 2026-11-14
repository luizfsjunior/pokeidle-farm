-- Fase 3b: dados do jogo (docs/design/fase-3b-catalogo-e-fila.md).
--
-- game_hunts   : as hunts do `welcome` (uma espécie cada).
-- game_species : a Pokedex dos creatures*.json públicos do jogo, com o estágio evolutivo.
-- game_catalog : versão de cada conjunto e as tabelas como vieram (captura, catalogoBolas).
--
-- O worker (service_role) substitui tudo de uma vez pelas funções abaixo, só quando a
-- versão muda. O painel só lê.

create table public.game_hunts (
  slug          text primary key,
  name          text,
  area          text,
  region        text,
  level         bigint not null,
  species_id    bigint not null,
  species_name  text,
  total_spawns  int,
  updated_at    timestamptz not null default now()
);
create index game_hunts_species on public.game_hunts (species_id);

create table public.game_species (
  species_id    bigint primary key,
  name          text,
  type1         text,
  type2         text,
  rarity        text,
  hunt_level    bigint,
  evolves_to    bigint,
  evolve_level  int,
  stage         text not null check (stage in ('first_of_three', 'middle', 'last')),
  data          jsonb not null default '{}'::jsonb,
  updated_at    timestamptz not null default now()
);

create table public.game_catalog (
  key         text primary key,
  version     text not null,
  data        jsonb,
  updated_at  timestamptz not null default now()
);

alter table public.game_hunts   enable row level security;
alter table public.game_species enable row level security;
alter table public.game_catalog enable row level security;

create policy read_game_hunts   on public.game_hunts   for select to authenticated using (true);
create policy read_game_species on public.game_species for select to authenticated using (true);
create policy read_game_catalog on public.game_catalog for select to authenticated using (true);

-- Substitui as hunts e grava as tabelas e a versão (atômico).
create function public.replace_game_hunts(p_version text, p_hunts jsonb, p_tables jsonb)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.game_hunts
   where slug not in (select h->>'slug' from jsonb_array_elements(p_hunts) h);

  insert into public.game_hunts
         (slug, name, area, region, level, species_id, species_name, total_spawns, updated_at)
  select h->>'slug', h->>'name', h->>'area', h->>'region', (h->>'level')::bigint,
         (h->>'species_id')::bigint, h->>'species_name', (h->>'total_spawns')::int, now()
    from jsonb_array_elements(p_hunts) h
  on conflict (slug) do update
     set name = excluded.name, area = excluded.area, region = excluded.region,
         level = excluded.level, species_id = excluded.species_id,
         species_name = excluded.species_name, total_spawns = excluded.total_spawns,
         updated_at = now();

  insert into public.game_catalog (key, version, data, updated_at)
  select t.key, p_version, t.value, now() from jsonb_each(p_tables) t
  union all
  select 'hunts', p_version, null, now()
  on conflict (key) do update
     set version = excluded.version, data = excluded.data, updated_at = now();
end;
$$;

-- Substitui a Pokedex e grava a versão (com os ETags em p_meta).
create function public.replace_game_species(p_version text, p_rows jsonb, p_meta jsonb)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.game_species
   where species_id not in (select (r->>'species_id')::bigint from jsonb_array_elements(p_rows) r);

  insert into public.game_species
         (species_id, name, type1, type2, rarity, hunt_level, evolves_to, evolve_level,
          stage, data, updated_at)
  select (r->>'species_id')::bigint, r->>'name', r->>'type1', r->>'type2', r->>'rarity',
         (r->>'hunt_level')::bigint, (r->>'evolves_to')::bigint, (r->>'evolve_level')::int,
         r->>'stage', coalesce(r->'data', '{}'::jsonb), now()
    from jsonb_array_elements(p_rows) r
  on conflict (species_id) do update
     set name = excluded.name, type1 = excluded.type1, type2 = excluded.type2,
         rarity = excluded.rarity, hunt_level = excluded.hunt_level,
         evolves_to = excluded.evolves_to, evolve_level = excluded.evolve_level,
         stage = excluded.stage, data = excluded.data, updated_at = now();

  insert into public.game_catalog (key, version, data, updated_at)
  values ('species', p_version, p_meta, now())
  on conflict (key) do update
     set version = excluded.version, data = excluded.data, updated_at = now();
end;
$$;

revoke all on function public.replace_game_hunts(text, jsonb, jsonb)   from public, anon, authenticated;
revoke all on function public.replace_game_species(text, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.replace_game_hunts(text, jsonb, jsonb)   to service_role;
grant execute on function public.replace_game_species(text, jsonb, jsonb) to service_role;
