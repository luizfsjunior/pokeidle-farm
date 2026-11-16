-- Perfil: campos novos e o histórico diário (docs/design/painel-fase-1-dados.md).
--
-- `extra`: campos do estado como o jogo manda (passe, ginásios, guild, caixas, chocadeira, boss, ...),
-- para o painel mostrar sem mudar o worker a cada campo novo. `pokedex`: a Pokédex inteira
-- ({speciesId: {c, k, ...}}), para a Pokédex interativa.
--
-- `account_profile_daily`: uma linha por conta e dia (fuso de Brasília), com os números do perfil no fim
-- do dia. Preenchida por trigger a cada gravação do perfil (o worker não muda): a última do dia fica.

alter table public.account_profile
  add column extra   jsonb not null default '{}'::jsonb,
  add column pokedex jsonb not null default '{}'::jsonb;

create table public.account_profile_daily (
  account_id     uuid not null references public.accounts (id) on delete cascade,
  day            date not null,
  updated_at     timestamptz not null default now(),
  level          int,
  xp             numeric,
  gold           numeric,
  gems           numeric,
  diamonds       numeric,
  pokemon_count  int,
  shiny_count    int,
  dex_seen       int,
  dex_caught     int,
  primary key (account_id, day)
);

alter table public.account_profile_daily enable row level security;
create policy own_account_profile_daily on public.account_profile_daily
  for select to authenticated
  using (account_id in (select id from public.accounts where owner_id = (select auth.uid())));

create or replace function public.account_profile_to_daily()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.account_profile_daily as d
         (account_id, day, updated_at, level, xp, gold, gems, diamonds, pokemon_count, shiny_count,
          dex_seen, dex_caught)
  values (new.account_id, (new.updated_at at time zone 'America/Sao_Paulo')::date, new.updated_at,
          new.level, new.xp, new.gold, new.gems, new.diamonds, new.pokemon_count, new.shiny_count,
          new.dex_seen, new.dex_caught)
  on conflict (account_id, day) do update
     set updated_at = excluded.updated_at, level = excluded.level, xp = excluded.xp,
         gold = excluded.gold, gems = excluded.gems, diamonds = excluded.diamonds,
         pokemon_count = excluded.pokemon_count, shiny_count = excluded.shiny_count,
         dex_seen = excluded.dex_seen, dex_caught = excluded.dex_caught
   where excluded.updated_at >= d.updated_at;
  return new;
end;
$$;

revoke all on function public.account_profile_to_daily() from public, anon, authenticated;

create trigger account_profile_daily_sync
  after insert or update on public.account_profile
  for each row execute function public.account_profile_to_daily();

-- o dia de hoje já começa com o perfil atual
insert into public.account_profile_daily
       (account_id, day, updated_at, level, xp, gold, gems, diamonds, pokemon_count, shiny_count,
        dex_seen, dex_caught)
select account_id, (updated_at at time zone 'America/Sao_Paulo')::date, updated_at, level, xp, gold,
       gems, diamonds, pokemon_count, shiny_count, dex_seen, dex_caught
  from public.account_profile
on conflict do nothing;
