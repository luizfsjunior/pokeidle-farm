-- Coleção completa de cada conta: um pokémon por linha (equipe, depot e Coleção), para o painel
-- mostrar e montar a equipe sem abrir o jogo (docs/design/conta-v2.md, seções 1.2 e 7).
-- O worker atualiza só os pokémons que mudaram (pkMud), apaga os que saíram (pkFora) e
-- ressincroniza tudo no welcome. Cresce com a coleção, não com o tempo: < 5 MB com 4 contas.

create table public.account_pokemon (
  account_id  uuid not null references public.accounts (id) on delete cascade,
  pokemon_id  bigint not null,
  species_id  int,
  slot        int,                              -- 0 a 4 na equipe; null no depot/Coleção
  data        jsonb not null default '{}'::jsonb,  -- profile.compact_pokemon
  updated_at  timestamptz not null default now(),
  primary key (account_id, pokemon_id)
);

create index account_pokemon_species on public.account_pokemon (account_id, species_id);

alter table public.account_pokemon enable row level security;
create policy own_account_pokemon on public.account_pokemon
  for select to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())));
-- escrita: só a service_role (worker), que ignora RLS
