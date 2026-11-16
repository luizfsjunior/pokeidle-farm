-- Preço de referência robusto: a mediana das vendas reais, por unidade (docs/design/preco-de-referencia.md).
--
-- A "média de 7 dias" do market.medias é puxada por poucas vendas caras: uma transferência de gemas entre
-- contas (1 pedra por 5.000 gemas) infla a média de um item com pouco volume. Em 16/11 a Water Stone tinha
-- média ~30 com 4.607 unidades anunciadas a 2.
--
-- Fonte: as respostas `market.historicoGlobal` que o market_prices grava (`market.reply`, aba
-- `historicoGlobal`). Cada linha é uma venda: {id, em (ms), tipo, bruto (total), moeda, descricao
-- ("135× Bronze Boss Token"), vendedor, comprador}. A mesma venda aparece em várias varreduras: conta uma vez.
--
-- Regras:
-- - preço por unidade = bruto / quantidade da descrição (sem "N×", 1 unidade);
-- - fora: vendas em que uma das nossas contas compra ou vende (transferência ou venda nossa);
-- - fora: vendas acima de p_outlier × a mediana simples do item, ou abaixo de 1/p_outlier dela;
-- - referência = mediana ponderada por unidades das vendas que sobram (o preço em que metade das unidades
--   vendeu).
--
-- security invoker: pelo painel, o RLS de events limita às respostas das próprias contas.

create or replace function public.market_reference(p_days int default 7, p_outlier numeric default 3)
returns table (
  item_name      text,
  item_id        bigint,
  currency       text,
  sales          int,      -- vendas que entraram na referência
  units          numeric,
  median_unit    numeric,  -- a referência
  mean_unit      numeric,  -- média simples das mesmas vendas, para comparar
  raw_mean_unit  numeric,  -- média por unidade de todas as vendas (com outliers), parecida com a do jogo
  outliers       int,      -- vendas descartadas por preço fora da faixa
  own            int,      -- vendas descartadas por envolver uma conta nossa
  last_sale_at   timestamptz
)
language sql
stable
set search_path = ''
as $$
  with lines as (
    select distinct on (l->>'id')
           l->>'id' as sale_id,
           to_timestamp((l->>'em')::numeric / 1000) as sold_at,
           coalesce(l->>'moeda', 'orb') as currency,
           (l->>'bruto')::numeric as gross,
           l->>'descricao' as descr,
           l->>'vendedor' as seller,
           l->>'comprador' as buyer
      from public.events e
      cross join lateral jsonb_array_elements(
             case when jsonb_typeof(e.raw->'linhas') = 'array' then e.raw->'linhas' else '[]'::jsonb end) l
     where e.type = 'market.reply'
       and e.data->>'aba' = 'historicoGlobal'
       and e.received_at >= now() - make_interval(days => p_days + 1)
       and coalesce(l->>'tipo', 'item') = 'item'
       and l->>'id' is not null
       and jsonb_typeof(l->'bruto') = 'number'
       and jsonb_typeof(l->'em') = 'number'
     order by l->>'id', e.received_at desc
  ),
  parsed as (
    select s.*,
           coalesce((regexp_match(s.descr, '^\s*([0-9]+)\s*[×xX]\s*'))[1]::numeric, 1) as qty,
           btrim(regexp_replace(s.descr, '^\s*[0-9]+\s*[×xX]\s*', '')) as name,
           exists (select 1 from public.accounts a where a.nick in (s.seller, s.buyer)) as is_own
      from lines s
     where s.sold_at >= now() - make_interval(days => p_days)
       and s.descr is not null
  ),
  priced as (
    select p.*, p.gross / nullif(p.qty, 0) as unit from parsed p where p.qty > 0
  ),
  base as (
    select name, currency,
           percentile_cont(0.5) within group (order by unit) as m,
           sum(gross) / nullif(sum(qty), 0) as raw_mean
      from priced where not is_own
     group by name, currency
  ),
  clean as (
    select p.name, p.currency, p.unit, p.qty, p.sold_at,
           sum(p.qty) over (partition by p.name, p.currency order by p.unit, p.sale_id) as cum,
           sum(p.qty) over (partition by p.name, p.currency) as total
      from priced p
      join base b using (name, currency)
     where not p.is_own
       and p.unit <= b.m * p_outlier
       and p.unit >= b.m / p_outlier
  ),
  agg as (
    select name, currency,
           count(*)::int as sales,
           sum(qty) as units,
           min(unit) filter (where cum >= total / 2.0) as wmedian,
           avg(unit) as mean_unit,
           max(sold_at) as last_sale_at
      from clean
     group by name, currency
  )
  select a.name, gi.item_id, a.currency, a.sales, a.units, round(a.wmedian, 2), round(a.mean_unit, 2),
         round(b.raw_mean, 2),
         (select count(*)::int from priced p
           where p.name = a.name and p.currency = a.currency and not p.is_own) - a.sales,
         (select count(*)::int from priced p where p.name = a.name and p.currency = a.currency and p.is_own),
         a.last_sale_at
    from agg a
    join base b using (name, currency)
    left join lateral (select i.item_id from public.game_items i where i.name = a.name
                        order by i.item_id limit 1) gi on true
   order by a.name, a.currency;
$$;

grant execute on function public.market_reference(int, numeric) to authenticated, service_role;
