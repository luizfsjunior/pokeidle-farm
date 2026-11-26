-- Aviso de teste no Discord pelo painel (notify.test, plugin notifier, épico A).
-- O worker manda um embed para o DISCORD_WEBHOOK_URL do .env; nada é gravado além do comando.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move',
  'center.heal', 'team.apply', 'collection.move', 'depot.sell', 'shop.buy', 'market.sell', 'market.cancel',
  'incubator.put', 'outland.tier', 'notify.test'));
