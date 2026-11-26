-- Aviso de "worker inteiro caiu" (épico A, pergunta 2 do plano; OK do Luiz em 26/11).
--
-- O plugin notifier avisa a queda de uma conta, mas se o droplet ou o container caem ninguém avisa,
-- porque quem avisa é o worker. Aqui o próprio Supabase confere a cada 5 min:
--   - o worker renova o lease de cada conta a cada 30 s (ttl 90 s);
--   - com conta de farm habilitada e nenhum lease vivo há 10 min, manda um aviso pelo webhook;
--   - quando um lease volta, manda o "voltou" com quanto tempo ficou fora.
-- A URL do webhook fica no Vault (segredo `discord_webhook_url`), gravada pelo worker ao subir
-- (set_notify_settings, a partir do DISCORD_WEBHOOK_URL do .env). O painel não lê o Vault.
-- Uma linha só de estado (worker_watch); nada cresce com o tempo.

create extension if not exists pg_net;

create table public.worker_watch (
  id           int primary key default 1 check (id = 1),
  down_since   timestamptz,
  notified_at  timestamptz,
  checked_at   timestamptz
);
insert into public.worker_watch (id) values (1);
alter table public.worker_watch enable row level security;  -- sem policy: só a service_role

-- O worker grava o webhook e a base dos links do painel no Vault (cria ou atualiza; vazio apaga).
create function public.set_notify_settings(p_webhook text, p_panel_url text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_name text;
  v_value text;
  v_id uuid;
begin
  foreach v_name in array array['discord_webhook_url', 'panel_url'] loop
    v_value := nullif(btrim(case v_name when 'discord_webhook_url' then p_webhook else p_panel_url end), '');
    select id into v_id from vault.secrets where name = v_name;
    if v_value is null then
      delete from vault.secrets where id = v_id;
    elsif v_id is null then
      perform vault.create_secret(v_value, v_name, 'Avisos no Discord (plugin notifier)');
    else
      perform vault.update_secret(v_id, v_value);
    end if;
  end loop;
end;
$$;

revoke all on function public.set_notify_settings(text, text) from public, anon, authenticated;
grant execute on function public.set_notify_settings(text, text) to service_role;

-- Confere os leases e avisa. Devolve o que fez (para o teste e para rodar à mão).
create function public.check_worker_alive(p_down_after interval default interval '10 minutes')
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_hook text;
  v_panel text;
  v_last timestamptz;
  v_holder text;
  v_watch public.worker_watch;
  v_minutes int;
  v_msg text;
  v_color int;
  v_out text := 'ok';
begin
  if not exists (select 1 from public.accounts where enabled and role = 'farm') then
    update public.worker_watch set down_since = null, notified_at = null, checked_at = now() where id = 1;
    return 'sem contas habilitadas';
  end if;

  select l.expires_at, l.holder into v_last, v_holder
    from public.account_leases l
    join public.accounts a on a.id = l.account_id and a.enabled and a.role = 'farm'
   order by l.expires_at desc
   limit 1;

  select * into v_watch from public.worker_watch where id = 1 for update;

  if v_last is not null and v_last > now() then
    -- vivo: se tinha avisado a queda, avisa a volta
    if v_watch.notified_at is not null then
      v_minutes := greatest(1, round(extract(epoch from now() - v_watch.down_since) / 60));
      v_msg := format('O worker voltou depois de %s min fora.', v_minutes);
      v_color := 3066993;  -- verde
      v_out := 'voltou';
    end if;
    update public.worker_watch set down_since = null, notified_at = null, checked_at = now() where id = 1;
  else
    -- sem lease vivo: a queda começou quando o último lease venceu (ou agora, se nunca houve)
    if v_watch.down_since is null then
      v_watch.down_since := coalesce(v_last, now());
    end if;
    v_out := 'fora';
    if v_watch.notified_at is null and now() - v_watch.down_since >= p_down_after then
      v_minutes := round(extract(epoch from now() - v_watch.down_since) / 60);
      v_msg := format(
        'Nenhuma conta com o worker há %s min (último lease: %s). O droplet ou o container pode ter caído.',
        v_minutes, coalesce(v_holder, 'nenhum')
      );
      v_color := 15158332;  -- vermelho
      v_watch.notified_at := now();
      v_out := 'caiu';
    end if;
    update public.worker_watch
       set down_since = v_watch.down_since, notified_at = v_watch.notified_at, checked_at = now()
     where id = 1;
  end if;

  if v_msg is null then
    return v_out;
  end if;
  select decrypted_secret into v_hook from vault.decrypted_secrets where name = 'discord_webhook_url';
  select decrypted_secret into v_panel from vault.decrypted_secrets where name = 'panel_url';
  if v_hook is null then
    return v_out || ' (sem webhook no Vault)';
  end if;
  perform net.http_post(
    url := v_hook,
    body := jsonb_build_object('embeds', jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
      'title', case v_out when 'caiu' then 'Worker fora do ar' else 'Worker de volta' end,
      'description', v_msg,
      'color', v_color,
      'url', nullif(rtrim(coalesce(v_panel, ''), '/'), ''),
      'timestamp', to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    )))),
    headers := '{"Content-Type": "application/json"}'::jsonb
  );
  return v_out;
end;
$$;

revoke all on function public.check_worker_alive(interval) from public, anon, authenticated;
grant execute on function public.check_worker_alive(interval) to service_role;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('worker-alive', '*/5 * * * *', 'select public.check_worker_alive()');
  end if;
end;
$$;
