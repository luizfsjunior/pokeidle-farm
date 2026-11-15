-- Fase 3b, passo 5: comando focus.set (docs/design/fase-3b-rank-ligado.md, seção 7).
-- O seletor de foco do painel grava o restock e o rank juntos.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set'));
