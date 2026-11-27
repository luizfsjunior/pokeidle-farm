# Números e histórico no painel (épico D)

O backlog de 26/11 pediu as 4 contas lado a lado com o que importa de relance, histórico de 7, 30 e 90 dias e um
layout de celular. Quase toda a base já existia; este épico junta numa tela e garante que 90 dias saiam de
agregados, nunca de eventos crus (o limite do Supabase Free é 500 MB).

## De onde vêm os números

| Número | Fonte | Guarda |
|---|---|---|
| XP, ouro, ouro líquido, abates, capturas, bolas, shiny, minutos ativos, desconexões, idas ao Centro | `metric_hourly` (por hora, conta e hunt; recalculada a cada 10 min a partir de `kill_minute` e `events`) | 100 dias |
| Os mesmos, depois de 95 dias | `metric_day` (por dia de Brasília, conta e métrica, sem hunt) | sem corte (uns 2 MB por ano) |
| Nível, XP total, gemas, diamantes, Pokédex, pokémons | `account_profile_daily` (retrato do perfil no fim do dia) | sem corte |
| HP do ativo, poções, revives, bolas | `account_profile` (a cada 2 min) | só o atual |

`metric_hourly` tinha 3,2 MB com 15 dias (27/11) e não tinha corte: num ano passaria de 75 MB. Agora o job
`metric-hourly-archive` (pg_cron, 05:17 UTC) soma os dias com mais de 95 dias em `metric_day` e apaga as horas com
mais de 100. O corte de 95 dias é fixo e o mesmo na leitura: dia com mais de 95 dias vem do arquivo, o resto das
horas. Os 5 dias de folga cobrem uma noite em que o job falhou.

`account_history(p_days)` devolve uma linha por conta e dia (uns 360 para 4 contas em 90 dias, abaixo do limite de
1.000 linhas do PostgREST), com zeros nos dias sem farm e nulos no perfil quando não há retrato. É `security
invoker`: as tabelas filtram por `account_id`, uma coluna de verdade, então o RLS não atrapalha o índice (ver
`painel-rls-lento`). Medido em 27/11 como `authenticated`: 12 ms para 90 dias.

## Telas

- **Contas** (`OverviewView.tsx`): cada cartão ganhou HP do ativo (aviso abaixo de 30%), poções, revives, bolas e
  "próximo nível em ~X h de farm" (XP que falta ÷ XP por hora ativa de hoje). XP/h, abates/h, gemas/h e ouro
  líquido/h já estavam lá.
- **Histórico** (`/historico`, novo): tabela do período por conta (nível e quanto subiu, XP, XP/h, ouro líquido e
  por hora, capturas e acerto, horas ativas e % do período, desconexões, gemas e variação) e um gráfico por conta
  da medida escolhida. As contas ficam lado a lado em gráficos separados na mesma escala, em vez de 4 linhas num
  gráfico só: 4 cores não ficam distinguíveis para daltônicos no tema escuro (validado com a skill de dataviz).
  Nível e gemas usam a escala de cada conta.
- **Hunts**: período de 90 dias e coluna XP/h; a gaveta da hunt também mostra XP por hora.
- **Celular**: a barra de abas embaixo e a gaveta da hunt como janela que sobe de baixo já existiam
  (`MobileNav.tsx`, `.drawer` no CSS). O Histórico entra em "Mais".

## Fora deste PR

- `kill_minute` continua com 14 dias de retenção. Como o histórico agora vem só dos agregados, dá para baixar
  para 8 dias (o Mercado e a liquidez olham 7) e economizar uns 25 MB. Ficou para depois, como combinado.
