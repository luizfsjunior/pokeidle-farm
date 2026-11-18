# Retenção dos eventos

Em 18/11 o Supabase avisou que o banco passou de 0,5 GB, o limite do plano grátis. O banco tinha 668 MB,
e a tabela `events` sozinha ocupava 646 MB (500 mil linhas).

| tipo | linhas | tamanho |
|---|---|---|
| `state.patch` | 270 mil | 402 MB |
| `kill` | 102 mil | 64 MB |
| `battle.cura` | 54 mil | 10 MB |
| o resto | — | < 10 MB cada |

## O que muda

- **O worker deixa de gravar `state.patch`** (`events.NOT_PERSISTED`). O patch continua passando pelo barramento: o
  perfil, o tradutor e os plugins usam. Do banco, nada lia esse evento: o que o painel mostra da conta vem de
  `account_profile`.
- **Retenção** (`prune_events()`, todo dia às 04:23 UTC pelo pg_cron). As somas por hora (`metric_hourly`, de onde
  saem as hunts de 24 h, 7 e 30 dias) ficam guardadas; o evento cru só serve às janelas curtas:
  - volumosos (`kill`, `capture_attempt`, `item.consumed`, ~50 MB/dia com 4 contas): 4 dias;
  - ruído (`battle.cura`, `wild_fled`, `action.sent`, `unknown`): 2 dias;
  - o resto (capturas, níveis, vendas, planos): 30 dias.
- **A migração reescreve a tabela** com `CLUSTER`. Sem isso, o espaço apagado só ficaria livre para reuso, e o
  tamanho do banco que o Supabase cobra não cairia.

O banco deve ficar em torno de 250 MB a 300 MB.

Custo: as contas que olham 7 dias de evento cru passam a ver 4. São a liquidez dos drops (`evaluation_liquidity`) e a
taxa de captura por hunt do rank (`rank_hunt_stats`). As hunts e os gráficos não mudam, porque leem as somas por hora.
