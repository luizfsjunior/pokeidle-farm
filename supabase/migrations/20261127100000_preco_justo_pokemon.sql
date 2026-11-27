-- Preço justo de pokémon no Mercado (épico B; docs/design/preco-justo-pokemon.md).
--
-- 1. market_pokemon_sales: uma linha por venda de pokémon vista no histórico global (market.historicoGlobal,
--    que o market_prices varre a cada 6 h). Só a ficha que importa para o preço, sem nomes de jogadores.
--    Preenchida por um gatilho em events (o worker não muda) e guardada 90 dias.
-- 2. pokemon_net_gems(): o que o vendedor recebe depois da comissão por faixa (13% / 10% / 7,5%).
-- 3. pokemon_fair_price(): preço justo de uma ficha a partir das vendas comparáveis.
-- 4. pokemon_prices(conta): o preço justo de cada pokémon da coleção, para o painel.
-- 5. pokemon_listing_verdicts(): veredito dos pokémon anunciados na última varredura da vitrine.

-- 1. Vendas -------------------------------------------------------------------------------------------

create table public.market_pokemon_sales (
  sale_id       bigint primary key,         -- id da venda no histórico global
  sold_at       timestamptz not null,
  species_id    int not null,               -- a forma é outra espécie (Mega, "Furious Scizor"...)
  name          text,
  shiny         boolean not null default false,
  potency       smallint,
  grade         numeric(6, 3),              -- a nota do jogo (0 a 10)
  quality       numeric(6, 3),
  level         int,
  power         int,
  iv_total      smallint,
  refine_total  smallint,
  tm_aoe        boolean not null default false,
  tm_physical   boolean not null default false,
  tm_elemental  text,
  price         numeric not null,           -- bruto, o que o comprador pagou
  currency      text not null default 'orb',
  is_own        boolean not null default false  -- uma das nossas contas comprou ou vendeu
);

create index market_pokemon_sales_comp
  on public.market_pokemon_sales (species_id, shiny, sold_at desc);

alter table public.market_pokemon_sales enable row level security;
-- dados do jogo inteiro, não de uma conta: qualquer usuário do painel lê
create policy read_market_pokemon_sales on public.market_pokemon_sales
  for select to authenticated using (true);
-- escrita: só o gatilho (security definer) e a service_role

-- tira as vendas de pokémon de uma resposta market.reply (aba historicoGlobal)
create or replace function public.extract_pokemon_sales(p_raw jsonb)
returns int
language sql
security definer
set search_path = ''
as $$
  with ins as (
    insert into public.market_pokemon_sales as s (
      sale_id, sold_at, species_id, name, shiny, potency, grade, quality, level, power, iv_total,
      refine_total, tm_aoe, tm_physical, tm_elemental, price, currency, is_own)
    select (l->>'id')::bigint,
           to_timestamp((l->>'em')::numeric / 1000),
           (f->>'speciesId')::int,
           f->>'nome',
           coalesce((f->>'shiny')::boolean, false),
           (f->>'potencia')::smallint,
           (f->>'nota')::numeric,
           (f->>'quality')::numeric,
           (f->>'level')::int,
           (f->>'poder')::int,
           (f->>'ivTotal')::smallint,
           (f->>'refinoTotal')::smallint,
           coalesce((f->>'tmAoe')::boolean, false),
           coalesce((f->>'tmFisico')::boolean, false),
           f->>'tmElemental',
           (l->>'bruto')::numeric,
           coalesce(l->>'moeda', 'orb'),
           exists (select 1 from public.accounts a where a.nick in (l->>'vendedor', l->>'comprador'))
      from jsonb_array_elements(
             case when jsonb_typeof(p_raw->'linhas') = 'array' then p_raw->'linhas' else '[]'::jsonb end) l
      cross join lateral (select l->'ficha' as f) x
     where l->>'tipo' = 'pokemon'
       and jsonb_typeof(l->'id') = 'number'
       and jsonb_typeof(l->'em') = 'number'
       and jsonb_typeof(l->'bruto') = 'number'
       and jsonb_typeof(f) = 'object'
       and jsonb_typeof(f->'speciesId') = 'number'
    on conflict (sale_id) do nothing
    returning 1
  )
  select count(*)::int from ins;
$$;

create or replace function public.events_pokemon_sales_trigger()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.data->>'aba' = 'historicoGlobal' then
    -- uma ficha estranha nunca pode derrubar a gravação do evento
    begin
      perform public.extract_pokemon_sales(new.raw);
    exception when others then
      raise warning 'extract_pokemon_sales: %', sqlerrm;
    end;
  end if;
  return null;
end;
$$;

create trigger events_pokemon_sales
  after insert on public.events
  for each row
  when (new.type = 'market.reply')
  execute function public.events_pokemon_sales_trigger();

-- o que já está guardado (as respostas vivem 30 dias em events)
do $$
declare r record;
begin
  for r in select e.raw from public.events e
            where e.type = 'market.reply' and e.data->>'aba' = 'historicoGlobal' loop
    begin
      perform public.extract_pokemon_sales(r.raw);
    exception when others then
      raise warning 'extract_pokemon_sales: %', sqlerrm;
    end;
  end loop;
end $$;

create or replace function public.purge_market_pokemon_sales()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare v bigint;
begin
  delete from public.market_pokemon_sales where sold_at < now() - interval '90 days';
  get diagnostics v = row_count;
  return v;
end;
$$;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('market-pokemon-sales-purge', '53 4 * * *',
                          'select public.purge_market_pokemon_sales()');
  end if;
end $$;

-- 2. Comissão -----------------------------------------------------------------------------------------

-- Pokémon vendido em gemas paga por faixa, como imposto de renda: 13% até 500, 10% de 500 a 5.000 e
-- 7,5% acima (docs/regras-do-jogo.md, Mercado). 2.000 gemas → 1.785.
create or replace function public.pokemon_net_gems(p_gross numeric)
returns numeric
language sql
immutable
set search_path = ''
as $$
  select round(p_gross
               - 0.13  * least(greatest(p_gross, 0), 500)
               - 0.10  * least(greatest(p_gross - 500, 0), 4500)
               - 0.075 * greatest(p_gross - 5000, 0), 2);
$$;

-- 3. Preço justo de uma ficha ------------------------------------------------------------------------
--
-- Comparáveis: vendas dos últimos p_days, sem as nossas, da mesma espécie (a forma já é outra espécie),
-- mesmo shiny, mesma potência, mesmo TM de área/físico e nível entre metade e o dobro. Com menos de
-- p_min_sales, a potência relaxa para a faixa (1–3, 4, 5). Vendas acima de 3× ou abaixo de 1/3 da mediana
-- simples ficam fora (transferências de gemas entre contas de um mesmo jogador).
--
-- Cada venda pesa recência × nota parecida: exp(-dias/7) × exp(-|Δnota|/0,5). Os preços saem como
-- percentis ponderados: rápido = 25%, justo = 50%, esperar = 75%. A nota parecida é o ajuste pela nota.
-- Menos de p_min_sales comparáveis: confidence = 'low' ("poucas referências"), os preços vêm mesmo assim
-- só para mostrar, e nenhum veredito sai deles.
create or replace function public.pokemon_fair_price(
  p_species_id int,
  p_shiny boolean,
  p_potency int,
  p_grade numeric,
  p_level int,
  p_tm_aoe boolean default false,
  p_tm_physical boolean default false,
  p_days int default 30,
  p_min_sales int default 5
)
returns table (
  fair        numeric,   -- bruto, preço justo (percentil 50 ponderado)
  quick       numeric,   -- bruto, para vender rápido (25%)
  patient     numeric,   -- bruto, para esperar (75%)
  fair_net    numeric,   -- o que entra depois da comissão
  median      numeric,   -- mediana simples das comparáveis (sem pesos)
  sales       int,       -- comparáveis que entraram
  outliers    int,
  match       text,      -- 'exact' (mesma potência) ou 'band' (faixa de potência)
  confidence  text,      -- 'ok' ou 'low'
  top_pct     numeric,   -- raridade: % das vendas da espécie (mesmo shiny) com nota >= a desta ficha
  species_sales int,     -- vendas da espécie (mesmo shiny) no período, base do top_pct
  last_sale_at timestamptz
)
language sql
stable
set search_path = ''
as $$
  with params as (
    select coalesce(p_potency, 1) as pot,
           case when coalesce(p_potency, 1) <= 3 then 1 else coalesce(p_potency, 1) end as band,
           greatest(coalesce(p_level, 1), 1) as lvl
  ),
  pool as (
    select s.*,
           case when coalesce(s.potency, 1) <= 3 then 1 else coalesce(s.potency, 1) end as band
      from public.market_pokemon_sales s
     where s.species_id = p_species_id
       and s.shiny = coalesce(p_shiny, false)
       and s.currency = 'orb'
       and not s.is_own
       and s.sold_at >= now() - make_interval(days => p_days)
  ),
  candidates as (
    select p.*, (p.potency = pr.pot) as exact
      from pool p, params pr
     where p.band = pr.band
       and p.tm_aoe = coalesce(p_tm_aoe, false)
       and p.tm_physical = coalesce(p_tm_physical, false)
       and greatest(coalesce(p.level, 1), 1) between pr.lvl / 2.0 and pr.lvl * 2.0
  ),
  chosen as (
    -- mesma potência se der; senão a faixa
    select c.*,
           case when (select count(*) from candidates where exact) >= p_min_sales then 'exact' else 'band' end
             as match
      from candidates c
  ),
  picked as (
    select * from chosen where match = 'band' or exact
  ),
  base as (
    select percentile_cont(0.5) within group (order by price) as m from picked
  ),
  clean as (
    select p.*,
           exp(-extract(epoch from now() - p.sold_at) / 86400.0 / 7)
             * exp(-abs(coalesce(p.grade, 0) - coalesce(p_grade, p.grade, 0)) / 0.5) as w
      from picked p, base b
     where p.price <= b.m * 3 and p.price >= b.m / 3
  ),
  cum as (
    select price, w,
           sum(w) over (order by price, sale_id) / nullif(sum(w) over (), 0) as c
      from clean
  ),
  agg as (
    select min(price) filter (where c >= 0.25) as q25,
           min(price) filter (where c >= 0.5)  as q50,
           min(price) filter (where c >= 0.75) as q75
      from cum
  ),
  rarity as (
    select count(*)::int as n,
           case when count(*) = 0 or p_grade is null then null
                else round(100.0 * count(*) filter (where grade >= p_grade) / count(*), 1) end as top
      from pool
  )
  select a.q50, a.q25, a.q75, public.pokemon_net_gems(a.q50),
         round((select percentile_cont(0.5) within group (order by price) from clean)::numeric, 2),
         (select count(*)::int from clean),
         (select count(*)::int from picked) - (select count(*)::int from clean),
         coalesce((select match from picked limit 1), 'band'),
         case when (select count(*) from clean) >= p_min_sales then 'ok' else 'low' end,
         r.top, r.n,
         (select max(sold_at) from clean)
    from agg a, rarity r;
$$;

-- veredito de um preço pedido contra o justo (do ponto de vista de quem compra)
create or replace function public.pokemon_price_verdict(p_price numeric, p_fair numeric, p_confidence text)
returns text
language sql
immutable
set search_path = ''
as $$
  select case
    when p_confidence is distinct from 'ok' or p_fair is null or p_fair <= 0 or p_price is null
      then 'poucas referências'
    when p_price <= p_fair * 0.60 then 'excepcional'
    when p_price <= p_fair * 0.80 then 'ótimo'
    when p_price <= p_fair * 0.95 then 'bom'
    when p_price <= p_fair * 1.15 then 'justo'
    else 'caro'
  end;
$$;

-- 4. A coleção de uma conta ---------------------------------------------------------------------------

-- security invoker: pelo painel, o RLS de account_pokemon limita às contas do usuário
create or replace function public.pokemon_prices(p_account_id uuid, p_days int default 30, p_min_sales int default 5)
returns table (
  pokemon_id   bigint,
  species_id   int,
  fair         numeric,
  quick        numeric,
  patient      numeric,
  fair_net     numeric,
  median       numeric,
  sales        int,
  outliers     int,
  match        text,
  confidence   text,
  top_pct      numeric,
  species_sales int,
  last_sale_at timestamptz
)
language sql
stable
set search_path = ''
as $$
  select p.pokemon_id, p.species_id, f.*
    from public.account_pokemon p
    cross join lateral public.pokemon_fair_price(
      p.species_id,
      coalesce((p.data->>'shiny')::boolean, false),
      (p.data->>'potency')::int,
      (p.data->>'grade')::numeric,
      (p.data->>'level')::int,
      coalesce((p.data->>'tm_aoe')::boolean, false),
      coalesce((p.data->>'tm_physical')::boolean, false),
      p_days, p_min_sales) f
   where p.account_id = p_account_id
     and p.species_id is not null
     -- espécie sem nenhuma venda: nem calcula
     and exists (select 1 from public.market_pokemon_sales s
                  where s.species_id = p.species_id
                    and s.sold_at >= now() - make_interval(days => p_days));
$$;

-- 5. Anúncios da vitrine ------------------------------------------------------------------------------

-- Os pokémon anunciados na última varredura (market.listar, aba vitrine, últimas 24 h), cada um com o
-- preço justo da sua ficha e o veredito. A varredura pega os mais caros e os shiny, então a maioria sai
-- "caro": serve para ver o topo do mercado e conferir a regra.
create or replace function public.pokemon_listing_verdicts(p_hours int default 24, p_days int default 30,
                                                           p_min_sales int default 5)
returns table (
  listing_id  bigint,
  seen_at     timestamptz,
  name        text,
  species_id  int,
  shiny       boolean,
  potency     int,
  grade       numeric,
  level       int,
  price       numeric,
  fair        numeric,
  diff_pct    numeric,
  sales       int,
  confidence  text,
  top_pct     numeric,
  verdict     text
)
language sql
stable
set search_path = ''
as $$
  with lines as (
    select distinct on (l->>'id')
           (l->>'id')::bigint as listing_id, e.received_at as seen_at, l->'ficha' as f,
           (l->>'preco')::numeric as price
      from public.events e
      cross join lateral jsonb_array_elements(
             case when jsonb_typeof(e.raw->'linhas') = 'array' then e.raw->'linhas' else '[]'::jsonb end) l
     where e.type = 'market.reply'
       and e.data->>'aba' = 'vitrine'
       and e.received_at >= now() - make_interval(hours => p_hours)
       and l->>'tipo' = 'pokemon'
       and coalesce(l->>'moeda', 'orb') = 'orb'
       and jsonb_typeof(l->'id') = 'number'
       and jsonb_typeof(l->'preco') = 'number'
       and jsonb_typeof(l->'ficha'->'speciesId') = 'number'
       and not exists (select 1 from public.accounts a where a.nick = l->>'vendedor')
     order by l->>'id', e.received_at desc
  )
  select x.listing_id, x.seen_at, x.f->>'nome', (x.f->>'speciesId')::int,
         coalesce((x.f->>'shiny')::boolean, false), (x.f->>'potencia')::int, (x.f->>'nota')::numeric,
         (x.f->>'level')::int, x.price, fp.fair,
         case when fp.fair > 0 then round(100 * (x.price - fp.fair) / fp.fair, 1) end,
         fp.sales, fp.confidence, fp.top_pct,
         public.pokemon_price_verdict(x.price, fp.fair, fp.confidence)
    from lines x
    cross join lateral public.pokemon_fair_price(
      (x.f->>'speciesId')::int, coalesce((x.f->>'shiny')::boolean, false), (x.f->>'potencia')::int,
      (x.f->>'nota')::numeric, (x.f->>'level')::int, coalesce((x.f->>'tmAoe')::boolean, false),
      coalesce((x.f->>'tmFisico')::boolean, false), p_days, p_min_sales) fp
   order by x.price desc;
$$;

grant execute on function public.pokemon_net_gems(numeric) to authenticated, service_role;
grant execute on function public.pokemon_fair_price(int, boolean, int, numeric, int, boolean, boolean, int, int)
  to authenticated, service_role;
grant execute on function public.pokemon_price_verdict(numeric, numeric, text) to authenticated, service_role;
grant execute on function public.pokemon_prices(uuid, int, int) to authenticated, service_role;
grant execute on function public.pokemon_listing_verdicts(int, int, int) to authenticated, service_role;
revoke execute on function public.extract_pokemon_sales(jsonb) from public, anon, authenticated;
revoke execute on function public.purge_market_pokemon_sales() from public, anon, authenticated;
grant select on public.market_pokemon_sales to authenticated;
