-- Enquanto o worker do droplet não é reconstruído, ele ainda grava state.patch: 144 MB por dia em
-- 19/11 (o banco voltou a 378 MB em 17 h). Nada lê esse evento (docs/design/retencao-eventos.md):
-- a limpeza dele passa a rodar de hora em hora, guardando só a última hora. O espaço apagado é
-- reusado pelas próximas linhas, então o banco para de crescer sem reescrever a tabela.
-- Ver docs/design/conta-v2.md, seção 7.

set local statement_timeout = 0;

create or replace function public.prune_state_patches()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v bigint;
begin
  delete from public.events where type = 'state.patch' and received_at < now() - interval '1 hour';
  get diagnostics v = row_count;
  return v;
end;
$$;

revoke all on function public.prune_state_patches() from public, anon, authenticated;
grant execute on function public.prune_state_patches() to service_role;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('events-prune-state-patch', '41 * * * *', 'select public.prune_state_patches()');
  end if;
end;
$$;

select public.prune_state_patches();
