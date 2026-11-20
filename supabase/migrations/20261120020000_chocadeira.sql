-- Chocadeira pelo painel (incubator.put: põe um ovo da mochila numa vaga; choca sozinho no fim do tempo).

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move',
  'center.heal', 'team.apply', 'collection.move', 'depot.sell', 'shop.buy', 'market.sell', 'market.cancel',
  'incubator.put'));
