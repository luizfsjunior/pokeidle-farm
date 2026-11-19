-- Coleção e venda do Depot pelo painel (colecao.mover e shop.sellAllPokemons).
-- collection.move marca o pokémon como da Coleção (não é vendido) ou do Depot; depot.sell vende o Depot inteiro.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move',
  'center.heal', 'team.apply', 'collection.move', 'depot.sell'));
