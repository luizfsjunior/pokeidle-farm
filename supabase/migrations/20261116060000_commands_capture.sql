-- Alvo de captura pelo painel (docs/design/captura-alvo.md).
-- capture.start {species_id, hunt_slug, ball_id, count?, hours?} liga o plugin capture_target;
-- capture.stop desliga.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop'));
