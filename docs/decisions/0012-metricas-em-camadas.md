# 0012 — Métricas em camadas no Postgres

- **Status:** Aceita
- **Data:** 2026-11-12
- **Complementa:** [0008](0008-escopo-completo-modular.md), [0010](0010-supabase-desde-o-inicio.md)

## Contexto

O [ADR 0008](0008-escopo-completo-modular.md) pede métricas modulares e objetivos com previsão ao longo do tempo. Os eventos brutos crescem rápido (uns 11 mil por conta por dia, pelo simulador), então o painel não pode somar `events` a cada consulta. Faltava decidir onde agregar, em que formato e como prever objetivos raros, como "um Dratini com qualidade ≥ 1,5 e Atk e Spe ≥ 28", que podem nunca ter acontecido nos dados.

## Decisão

Agregar **dentro do Postgres**, em camadas, pela migration `20261112010000_metrics.sql`:

1. **`metric_hourly`** em formato longo: uma linha por conta, hora, hunt e métrica base, com o valor. Uma métrica base nova é uma coluna no `select` do refresh e uma linha em `metric_definitions`, sem mudar o schema.
2. **Refresh idempotente** (`refresh_metric_hourly`, apaga e reinsere as horas) e **incremental** (`refresh_metrics_incremental`, guiado pela nova coluna `events.inserted_at`). Assim, eventos antigos reenviados pelo buffer do worker também entram. Roda a cada 10 minutos pelo pg_cron.
3. **`metric_daily`** é uma view sobre a hora, com o dia no fuso de Brasília.
4. **`metric_definitions`** tem dois tipos: `base` (soma) e `ratio` (numerador ÷ denominador × escala). A razão sempre soma os dois lados no período antes de dividir, nunca tira média de médias. O "por hora" usa minutos ativos (minutos com pelo menos um abate), para não punir o tempo desconectado.
5. **`goals`** tem dois tipos: `metric`, para somar uma métrica base até o alvo, e `capture`, para capturar N pokémon que batem com um filtro de espécie, qualidade, potência, shiny e IVs. **`goal_progress()`** calcula o valor atual, o ritmo, a previsão de conclusão e se está no prazo. **`goal_snapshots`** guarda isso de hora em hora, para o painel mostrar a evolução.
6. **Previsão de captura** pelo produto das frações de cada critério nas capturas dos últimos 7 dias. Os sorteios dos Termos (§14) são independentes, então isso funciona mesmo sem nenhum caso igual ao objetivo nos dados. Cada fração é suavizada (+0,5), para um critério nunca visto não zerar a previsão. O shiny usa a taxa dos Termos, 1/24000. A chance de bater até o prazo usa a distribuição de Poisson.

O tradutor e o simulador passam a carimbar `hunt_slug` em `kill` e `capture_attempt`, para o agregado sair por hunt.

## Consequências

- O painel lê agregados pequenos, uns mil por dia com 3 contas, e não `events`. Isso também abre caminho para uma política de retenção do `raw` sem perder métricas.
- Mudou uma métrica? Basta `select public.refresh_metric_hourly('2026-01-01', now())`, porque os eventos brutos continuam sendo a fonte da verdade.
- O início de um objetivo de métrica é arredondado para a hora cheia.
- O ritmo usa as últimas 24 horas de relógio, incluindo o tempo parado. Isso é realista para prever, mas oscila nas primeiras horas.
- A previsão de captura assume critérios independentes. É uma aproximação quando o filtro combina a soma de IVs com IVs individuais, que são correlacionados.
- Os eventos simulados antes desta mudança não têm `hunt_slug` nos abates. É melhor apagá-los e gerar de novo.

## Alternativas consideradas

- **Agregar no worker (Python):** mais fácil de testar, mas cada worker veria só as próprias contas, e recalcular o histórico exigiria reprocessar fora do banco.
- **Materialized views:** o refresh é total e trava a view. O refresh incremental por hora é mais barato e aceita eventos atrasados.
- **Formato largo (uma coluna por métrica):** consultas mais simples, mas cada métrica nova exigiria uma migration.
- **Prever captura só pela taxa observada de casos iguais:** zero para objetivos raros, que são justamente os interessantes.
