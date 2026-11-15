-- Teste do hunt_summary (painel de hunts). Cria os próprios dados e apaga no fim.
\set ON_ERROR_STOP 1

insert into auth.users (id) values
  ('00000000-0000-0000-0000-0000000f0a01'), ('00000000-0000-0000-0000-0000000f0b02');
insert into public.accounts (id, owner_id, nick, role) values
  ('00000000-0000-0000-0000-00000f0ac001', '00000000-0000-0000-0000-0000000f0a01', 'hs-a', 'farm'),
  ('00000000-0000-0000-0000-00000f0bc001', '00000000-0000-0000-0000-0000000f0b02', 'hs-b', 'farm');
insert into public.metric_hourly (account_id, hour, hunt_slug, metric, value) values
  ('00000000-0000-0000-0000-00000f0ac001', date_trunc('hour', now()), 'x', 'kills', 100),
  ('00000000-0000-0000-0000-00000f0ac001', date_trunc('hour', now()), 'x', 'active_minutes', 6),
  ('00000000-0000-0000-0000-00000f0ac001', date_trunc('hour', now()) - interval '1 hour', 'x', 'kills', 50),
  ('00000000-0000-0000-0000-00000f0ac001', date_trunc('hour', now()) - interval '1 hour', 'x', 'drops_value_orb', 30),
  ('00000000-0000-0000-0000-00000f0ac001', date_trunc('hour', now()) - interval '3 days', 'x', 'kills', 999),
  ('00000000-0000-0000-0000-00000f0ac001', date_trunc('hour', now()), '', 'disconnects', 1),
  ('00000000-0000-0000-0000-00000f0bc001', date_trunc('hour', now()), 'x', 'kills', 7);

set role authenticated;
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-0000000f0a01', false);
do $$
declare
  r record;
begin
  select * into r from public.hunt_summary(now() - interval '1 day') where hunt_slug = 'x';
  assert r.kills = 150, format('kills %s ≠ 150 (fora da janela e de outro dono não contam)', r.kills);
  assert r.active_minutes = 6 and r.drops_value_orb = 30, 'minutos ou gemas errados';
  assert (select count(*) from public.hunt_summary(now() - interval '1 day')) = 1, 'hunt vazia apareceu';
  assert (select kills from public.hunt_summary(now() - interval '7 days') where hunt_slug = 'x') = 1149,
    'janela de 7 dias';
  assert (select count(*) from public.hunt_summary(now() - interval '1 day', '00000000-0000-0000-0000-00000f0bc001')) = 0,
    'conta alheia apareceu';
end;
$$;
reset role;

delete from public.metric_hourly where account_id in
  ('00000000-0000-0000-0000-00000f0ac001', '00000000-0000-0000-0000-00000f0bc001');
delete from public.accounts where nick in ('hs-a', 'hs-b');
delete from auth.users where id in ('00000000-0000-0000-0000-0000000f0a01', '00000000-0000-0000-0000-0000000f0b02');
do $$ begin raise notice 'hunt_summary: ok'; end $$;
