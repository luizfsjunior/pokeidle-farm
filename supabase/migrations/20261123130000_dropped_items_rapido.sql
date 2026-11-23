-- dropped_items abria o `data` de todo abate de events na janela (~50 mil num dia), com ou sem drop: 8,4 s, acima
-- dos 8 s do papel authenticated (erro 500 na tela do Mercado em 23/11). Só os abates com drop: usa o índice
-- parcial events_kill_drops (type = 'kill' e drops <> '[]') e cai para ~0,1 s. As linhas de kill_minute sem drop
-- também ficam de fora.
create or replace function public.dropped_items(p_since timestamptz, p_account uuid default null)
returns table (name text, qty numeric)
language sql
stable
set search_path = ''
as $$
  with src as (
    select k.drops
      from public.kill_minute k
     where k.minute >= date_trunc('minute', p_since)
       and k.drops <> '[]'::jsonb
       and (p_account is null or k.account_id = p_account)
    union all
    select e.data->'drops'
      from public.events e
     where e.type = 'kill' and (e.data->'drops') <> '[]'::jsonb
       and e.received_at >= p_since
       and (p_account is null or e.account_id = p_account)
  )
  select d->>'name', sum(coalesce(nullif(d->>'qty', '')::numeric, 1))
    from src
    cross join lateral jsonb_array_elements(
           case when jsonb_typeof(src.drops) = 'array' then src.drops else '[]'::jsonb end) d
   where d->>'name' is not null
   group by 1;
$$;
