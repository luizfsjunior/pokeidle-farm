-- Loja e Mercado pelo painel (docs/design/refatoracao-2026-11-20.md, seção 5):
-- shop.buy compra na loja do NPC; market.sell anuncia um item; market.cancel cancela um anúncio da conta.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move',
  'center.heal', 'team.apply', 'collection.move', 'depot.sell', 'shop.buy', 'market.sell', 'market.cancel'));
