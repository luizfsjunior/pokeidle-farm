-- Equipe pelo painel (docs/design/team-train.md).
-- team.active {pokemon_id} troca o pokémon ativo; team.move {pokemon_id, slot} põe na equipe
-- (slot 0 a 4) ou tira (slot null).

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move'));
