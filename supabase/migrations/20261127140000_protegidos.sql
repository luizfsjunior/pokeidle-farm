-- Pokémon protegidos (épico C1, docs/design/protegidos-e-bosses.md): a lista que nenhuma automação vende,
-- manda para o Depot, oferece, sacrifica ou troca. Só as marcas do painel ficam aqui; os motivos automáticos
-- (shiny, equipe, Coleção do jogo) saem do próprio pokémon em account_pokemon (worker/src/pokeidle_farm/protection.py).
--
-- O painel grava e apaga direto (RLS do dono, como team_drafts); o worker relê a cada minuto e na hora de
-- qualquer comando que mexe no Depot. Cresce com as marcas, não com o tempo: alguns KB.

create table public.protected_pokemon (
  account_id  uuid not null references public.accounts (id) on delete cascade,
  pokemon_id  bigint not null,
  note        text check (note is null or length(note) <= 200),
  created_at  timestamptz not null default now(),
  primary key (account_id, pokemon_id)
);

alter table public.protected_pokemon enable row level security;
create policy own_protected_pokemon on public.protected_pokemon
  for all to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())))
  with check (account_id in (select id from public.accounts where owner_id = (select auth.uid())));

grant select, insert, update, delete on public.protected_pokemon to authenticated;
