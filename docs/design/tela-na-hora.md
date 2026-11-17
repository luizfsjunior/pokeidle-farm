# Tela na hora

Pedido de 17/11: um comando ficava "feito", mas a tela só mudava minutos depois, porque o worker grava o
perfil a cada 2 minutos e o painel buscava o dado velho.

## Três partes

1. **Otimista** (`web/lib/optimistic.ts`): no "feito", o painel aplica o efeito previsível no cache.
   - Comandos tratados: tornar ativo, pôr e tirar da equipe, trocar de hunt, ligar e configurar plugin.
   - Para os que mexem no perfil, não busca de novo na hora: busca de novo 6 s depois, só se o Realtime
     não tiver trazido o dado antes.
2. **Gravação rápida no worker** (`plugins/profile.py`, `quick_s` = 2 s): um patch que muda o ativo (`activeId`),
   a hunt (`huntSlug`), tira um pokémon (`pkFora`) ou mexe no `slot` de alguém grava o perfil em 2 s, juntando os
   patches da mesma troca. O resto continua no intervalo de 2 minutos.
3. **Realtime** (`web/lib/query/realtime.tsx`): o painel assina `account_profile`, `strategy_configs` e
   `commands`. Quando uma linha muda, só as consultas que usam aquele dado são buscadas de novo, e as mudanças
   que chegam juntas viram uma busca só (400 ms). A migração `20261117020000_realtime_profile.sql` põe as duas
   primeiras tabelas na publicação. O RLS vale também para o Realtime.

Sem websocket (rede que bloqueia), o painel continua como antes: a busca a cada minuto e a do comando.
