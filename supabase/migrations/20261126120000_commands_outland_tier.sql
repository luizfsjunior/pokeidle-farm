-- Tier da Outland pelo painel (outland.tier: o número da Outland, ou o maior liberado sem número).
-- O plugin outland_tier já sobe o tier sozinho; o comando serve para escolher à mão.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move',
  'center.heal', 'team.apply', 'collection.move', 'depot.sell', 'shop.buy', 'market.sell', 'market.cancel',
  'incubator.put', 'outland.tier'));
