-- Painel lento (27/11): as leituras de events feitas como `authenticated` passavam pelo RLS
-- (own_events). Com RLS, o Postgres só usa no índice os filtros "leakproof"; o `data->>'campo'` não é,
-- então os índices de expressão events_action_by_action e events_market_reply_by_aba (20261123110000)
-- não serviam para o painel: ele lia o índice inteiro da conta e abria o `data` de cada linha.
-- Medido em 27/11 na conta luizfsjunior_1, ações de Mercado em 30 dias:
--   como postgres (sem RLS): 1,8 ms | como authenticated (painel): 6.400 ms (52 de 158 chamadas
--   passaram dos 8 s e deram erro 500 em 24 h)
-- market_reference: 570 ms sem RLS, 3.200 ms como authenticated (6 de 16 erros em 24 h).
-- Essas leituras ocupavam a CPU do banco (plano Free) e deixavam lentas as outras telas também.
--
-- O que muda:
-- 1. market_sales_events(): as quatro leituras de events da página de Vendas (economia/sales.ts) numa
--    função SECURITY DEFINER, que filtra as contas do dono (auth.uid()) por conta própria. Sem o RLS no
--    caminho, os índices de expressão valem. Uma ida ao banco em vez de quatro: 8 s (com erros) -> 6 ms.
-- 2. market_reference(): SECURITY DEFINER (o histórico do Mercado é o mesmo para todas as contas) e sem
--    as duas subconsultas por item (contavam as vendas de novo para cada um dos ~125 itens):
--    570 ms -> 90 ms com o mesmo resultado (conferido linha a linha em 27/11).
-- 3. pokemon_listing_verdicts(): SECURITY DEFINER pelo mesmo motivo (lê a vitrine do Mercado em events).
-- 4. prune_events(): as respostas da aba `item` do Mercado (o `raw` com a fila de anúncios de um item)
--    ficam 2 dias. O worker já tira delas o que importa na hora (market_asks); eram 10 mil linhas e 24 MB
--    em 27/11, o maior pedaço de events. Esta migration não apaga nada por si: o pg_cron roda o prune
--    às 04:23 UTC.

-- 1. Vendas do painel ---------------------------------------------------------------------------------

create or replace function public.market_sales_events(p_since timestamptz, p_account uuid default null)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  -- as contas de quem chamou: o mesmo filtro do RLS (own_events), escrito aqui para os índices valerem
  with mine as (
    select a.id from public.accounts a
     where a.owner_id = (select auth.uid())
       and (p_account is null or a.id = p_account)
  ),
  -- uma consulta por fonte, cada uma com o seu limite, para nenhuma lotar as outras
  ev as (
  (select e.received_at, e.account_id, e.type, e.data, e.raw
     from public.events e
    where e.type = 'market.reply' and e.data->>'aba' in ('meus', 'criado')
      and e.account_id in (select id from mine) and e.received_at >= p_since
    order by e.received_at desc limit 1500)
  union all
  (select e.received_at, e.account_id, e.type, e.data, null
     from public.events e
    where e.type in ('action.sent', 'action.blocked', 'action.failed')
      and e.data->>'action' in ('market.criar', 'market.cancelar', 'market.meus')
      and e.account_id in (select id from mine) and e.received_at >= p_since
    order by e.received_at desc limit 1000)
  union all
  -- os tipos vêm de worker/src/.../plugins/seller.py
  (select e.received_at, e.account_id, e.type, e.data, null
     from public.events e
    where e.type in ('seller.plan', 'seller.would', 'seller.failed', 'seller.probe')
      and e.account_id in (select id from mine) and e.received_at >= p_since
    order by e.received_at desc limit 300)
  union all
  (select e.received_at, e.account_id, e.type, e.data, e.raw
     from public.events e
    where e.type = 'unknown' and e.data->>'t' in ('venda', 'marketComprado', 'aviso', 'mktSorteio')
      and e.account_id in (select id from mine) and e.received_at >= p_since
    order by e.received_at desc limit 200)
  )
  -- um valor só (lista JSON): o PostgREST corta em 1.000 as funções que devolvem linhas
  select coalesce(jsonb_agg(to_jsonb(ev) order by ev.received_at desc), '[]'::jsonb) from ev;
$$;

revoke execute on function public.market_sales_events(timestamptz, uuid) from public, anon;
grant execute on function public.market_sales_events(timestamptz, uuid) to authenticated;

-- 2. Preço de referência ------------------------------------------------------------------------------
-- Mesma regra de 20261116030000 (docs/design/preco-de-referencia.md). O enable_nestloop desligado é porque
-- o Postgres estima 1 linha para cada CTE e cruzava itens x vendas (750 mil comparações); com ele, hash join.

create or replace function public.market_reference(p_days int default 7, p_outlier numeric default 3)
returns table (
  item_name     text,
  item_id       bigint,
  currency      text,
  sales         int,
  units         numeric,
  median_unit   numeric,
  mean_unit     numeric,
  raw_mean_unit numeric,
  outliers      int,
  own           int,
  last_sale_at  timestamptz
)
language sql
stable
security definer
set search_path = ''
set enable_nestloop = off
as $$
  with own as materialized (select coalesce(array_agg(a.nick), '{}') as nicks from public.accounts a),
  lines as (
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
           (array[s.seller, s.buyer] && o.nicks) as is_own
      from lines s
      cross join own o
     where s.sold_at >= now() - make_interval(days => p_days)
       and s.descr is not null
  ),
  priced as materialized (
    select p.*, p.gross / nullif(p.qty, 0) as unit from parsed p where p.qty > 0
  ),
  base as (
    select name, currency,
           percentile_cont(0.5) within group (order by unit) filter (where not is_own) as m,
           sum(gross) filter (where not is_own) / nullif(sum(qty) filter (where not is_own), 0) as raw_mean,
           (count(*) filter (where not is_own))::int as others,
           (count(*) filter (where is_own))::int as own
      from priced
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
         round(b.raw_mean, 2), b.others - a.sales, b.own, a.last_sale_at
    from agg a
    join base b using (name, currency)
    left join lateral (select i.item_id from public.game_items i where i.name = a.name
                        order by i.item_id limit 1) gi on true
   order by a.name, a.currency;
$$;

revoke execute on function public.market_reference(int, numeric) from public, anon;
grant execute on function public.market_reference(int, numeric) to authenticated, service_role;

-- 3. Vereditos da vitrine -----------------------------------------------------------------------------

alter function public.pokemon_listing_verdicts(int, int, int) security definer;
revoke execute on function public.pokemon_listing_verdicts(int, int, int) from public, anon;

-- 4. Retenção -----------------------------------------------------------------------------------------
create or replace function public.prune_events()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_noise bigint;
  v_old bigint;
  v_minutes bigint;
begin
  delete from public.events
   where received_at < now() - interval '2 days'
     and (type in ('state.patch', 'battle.cura', 'wild_fled')
          or (type in ('action.sent', 'action.blocked')
              and coalesce(data->>'action', '') not in ('market.criar', 'market.cancelar', 'market.meus'))
          or (type = 'unknown'
              and coalesce(data->>'t', '') not in ('venda', 'marketComprado', 'aviso', 'mktSorteio'))
          -- a fila de anúncios de um item: o worker grava o resumo em market_asks na hora
          or (type = 'market.reply' and data->>'aba' = 'item'));
  get diagnostics v_noise = row_count;
  -- os volumosos do worker antigo (o novo soma em kill_minute)
  delete from public.events
   where type in ('kill', 'capture_attempt', 'item.consumed')
     and received_at < now() - interval '1 day';
  get diagnostics v_old = row_count;
  v_noise := v_noise + v_old;
  delete from public.events where received_at < now() - interval '30 days';
  get diagnostics v_old = row_count;
  delete from public.kill_minute where minute < now() - interval '14 days';
  get diagnostics v_minutes = row_count;
  return v_noise + v_old + v_minutes;
end;
$$;
