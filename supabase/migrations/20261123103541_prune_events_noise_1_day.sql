-- Aplicada à mão em 23/11 (pelo MCP do Supabase): o banco tinha 558 MB, acima dos 500 MB do plano grátis, e
-- 225 mil `kill` em 4 dias ocupavam 141 MB. Os volumosos passam de 4 dias para 1; as somas por hora
-- continuam em metric_hourly. O arquivo existe para a integração do GitHub achar a versão já registrada.
-- Ver docs/design/retencao-eventos.md.
CREATE OR REPLACE FUNCTION public.prune_events()
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_noise bigint;
  v_old bigint;
begin
  -- plano Free (500 MB): kill/capture/item.consumed passam de 4 para 1 dia;
  -- os agregados ficam em metric_hourly
  delete from public.events
   where (type in ('state.patch', 'battle.cura', 'wild_fled', 'action.sent', 'unknown')
          and received_at < now() - interval '2 days')
      or (type in ('kill', 'capture_attempt', 'item.consumed')
          and received_at < now() - interval '1 day');
  get diagnostics v_noise = row_count;
  delete from public.events where received_at < now() - interval '30 days';
  get diagnostics v_old = row_count;
  return v_noise + v_old;
end;
$function$;
