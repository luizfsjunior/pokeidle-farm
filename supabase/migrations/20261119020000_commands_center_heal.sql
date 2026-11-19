-- Curar a equipe no Pokécenter pelo painel (centro.curar; docs/design/conta-v2.md, seção 5).
-- A vigia do worker cura sozinha; o comando é para quando o usuário quer mandar na hora.

alter table public.commands drop constraint commands_type_check;
alter table public.commands add constraint commands_type_check check (type in (
  'ping', 'account.enable', 'account.disable', 'session.reconnect', 'plugin.set', 'focus.set',
  'hunt.select', 'hunt.release', 'capture.start', 'capture.stop', 'team.active', 'team.move',
  'center.heal'));
