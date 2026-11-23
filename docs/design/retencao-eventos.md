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

## 23/11: 1 dia de retenção e abates por minuto

O banco voltou a passar do limite: 558 MB, 530 MB só na `events`. A retenção já funcionava, mas o volume não cabe:
~56 mil `kill` por dia com 4 contas (141 MB em 4 dias), ~90 mil `battle.cura` e ~34 mil `item.consumed`.

**Na hora** (aplicado à mão, migration `20261123103541_prune_events_noise_1_day.sql`): `kill`, `capture_attempt` e
`item.consumed` passaram de 4 dias para 1, e um `VACUUM FULL` devolveu o espaço. Banco: 558 MB → 257 MB.

### Abates por minuto

Solução definitiva (migration `20261123120000_kill_minute.sql`, `worker/src/pokeidle_farm/kill_minutes.py`):

- **A telemetria não grava mais um `kill` nem um `item.consumed` por linha.** Soma por minuto e grava uma linha em
  `kill_minute` quando o minuto fecha (ou quando a sessão para). São ~6 mil linhas por dia, em vez de ~90 mil.
- **Chave**: conta, sessão, minuto, hunt, espécie do pokémon ativo, dia sazonal e parte. A espécie e o dia sazonal
  entram porque o ritmo descontado do dia sazonal depende deles. A gravação é `on conflict do nothing`, então
  reenviar o buffer local não conta duas vezes; um abate que chega depois de o minuto ter sido gravado vai numa
  parte nova.
- **Colunas**: abates, XP, ouro (com a venda automática), soma do nível do ativo e abates com nível, drops somados por
  nome (`[{name, qty}]`) e o gasto com poções e revives.
- **`battle.cura` deixou de ser gravado** (`NOT_PERSISTED`): nada lia do banco.
- **Quem lia os abates**: `refresh_metric_hourly` (todas as métricas por hora), `evaluation_liquidity` e a tela do
  Mercado no painel. As três leem `kill_minute` mais os abates que ainda estão em `events`, por isso o worker antigo
  continua funcionando até ser atualizado. A tela e a liquidez usam a função nova `dropped_items(since, account)`.
- **Retenção de `kill_minute`**: 14 dias (a tela do Mercado e a liquidez olham 7).

Verificação: `supabase/tests/kill_minute_test.sql` grava os mesmos abates como eventos numa conta e como
`kill_minute` em outra e exige métricas idênticas. Nos dados reais (4 horas de 23/11), a função nova e a antiga deram as
mesmas 189 linhas de `metric_hourly`.

Custo: o abate individual (nome do selvagem, onda, slot, `raw`) não fica mais guardado. Nada lia esses campos do banco;
os plugins continuam recebendo o evento inteiro pelo barramento.
