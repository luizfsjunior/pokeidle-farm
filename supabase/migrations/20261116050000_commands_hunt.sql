-- Painel, fase 3: escolher a hunt pelo painel (docs/design/painel-fase-3.md).
-- hunt.select {slug, hours} liga o plugin hunt_hold com o prazo; hunt.release desliga.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release'));
