# Foco gemas, ritmo aprendido e arquivos do jogo

Status: **implementado** (15/11/2026), direto da [análise de 15/11](../analise-2026-11-15.md) (propostas A a F), sem
spec prévia, a pedido. As decisões abaixo foram tomadas na implementação e podem ser revistas.

## A. Ritmo aprendido (`pace.py`, usado pelo `rank` e pelo `gems`)

- `PaceBook` junta o histórico do banco (`rank_hunt_stats`, 14 dias) com os abates da sessão: uma hunt fica
  "medida" com `min_active_minutes` (5) minutos distintos com abate.
- Hunt nunca medida (`rates_for`): mediana das medidas do **mesmo nível**; senão, do **nível medido mais próximo
  abaixo** (hunts mais altas são mais lentas, então é a estimativa conservadora); sem nada abaixo, o mais próximo
  acima; sem nada medido, o ritmo médio da conta. Antes, toda hunt não medida usava o ritmo médio (~905/h), e as de
  nível 10 a 20 rendem 60 a 115/h.
- `rank`: replaneja (`reason: "rate_measured"`) quando o ritmo medido no alvo foge mais de 30% do que o plano supôs;
  com a histerese de 10%, troca na hora se outra hunt ficou melhor, sem esperar o timeout.
- `rank`: as espécies puladas da semana voltam do último `rank.plan` (até 12 h atrás) quando o plugin sobe de novo.

## B. Foco gemas (`gems_model.py`, `plugins/gems.py`, `hunt_switch.py`)

**Correção (15/11, à noite):** o preço de cada pedra passou a ser o menor entre a média de 7 dias e o menor anúncio
aberto ([fase-9-venda-de-pedras.md](fase-9-venda-de-pedras.md)): a Water Stone tinha média ~30 e 4.607 unidades a 2
gemas. As estimativas de gemas/h anteriores a isso estavam infladas.

**Modelo** (do código público do jogo, `/shared/loot-pedras.mjs` e `pedras-evolucao.mjs`): todo selvagem pode
dropar a pedra de evolução de cada um dos seus tipos, com 0,2% / 0,35% / 0,5% por abate conforme a posição na
cadeia evolutiva (espécie sem evolução conta como a última). Conferido: 0,26% de Water Stone em 4.260 abates de
Magikarp.

```
gemas/h(hunt) = abates/h × Σ_pedras chance × média de 7 dias em gemas
teto: de cada pedra conta no máximo max_market_share (10%) do que o Mercado vende por semana,
      menos o que as outras contas do worker já tiram dela
```

**Plugin `gems`** (config `GemsConfig`, `dry_run` padrão `true`):
- replaneja na subida, a cada `interval_min` (15), ao subir de nível e quando chegam preços novos; grava `gems.plan`
  com o alvo e as 5 melhores hunts;
- troca de hunt só se a melhor render mais que `1 + hysteresis` (15%) da atual;
- troca com o `HuntSwitcher` (as mesmas regras do rank: trava de combate e `trocaLivreEm` pelo relógio do servidor,
  timer para o fim da trava, confirmação pelo `hunt.changed`, nova tentativa em 60 s, no máximo 6 trocas por hora);
  falha vira `gems.failed`;
- não age se o `rank` estiver ligado sem `dry_run` (os dois brigariam pela hunt): `degraded: ["rank_acting"]`;
- com várias contas no worker, cada uma registra quanto tira de cada pedra (`_claims`) e as outras descontam.

**Foco no painel:** "Gemas (pedras)" no card Foco manda `focus.set` com `focus: "gems"`: `restock` em
`gold_xp_drop` (sem bola: o foco é abater rápido), `rank` desligado, `gems` ligado com `dry_run: false`.

**Gemas é o foco padrão** (decidido em 15/11): `luizfsjunior_1` passou para gemas às 20:51 UTC (foi para o Geodude), e
uma conta nova, sem nada configurado, aparece no card Foco com "Gemas" selecionado (é preciso salvar para ligar).

## C. Wiki e fórmulas no banco (`GameFilesSync`, tabela `game_files`)

Uma vez por dia, por ETag: `pokepedia.mjs` (a wiki do jogo, ~1 MB, 45 capítulos) e os módulos `/shared/` que importam
para o farm (`loot-pedras`, `pedras-evolucao`, `taxa-mercado`, `recompensa-hunt`, `sell-value`, `tipo-efetividade`,
`captura-degrau`). As constantes das pedras vão para `game_catalog` (`loot_stones`), e o `gems` usa as do banco quando
existem (as do código são o padrão). O conteúdo do jogo fica só no banco (privado), não no repositório (público).

## D. "Compensa?"

- `evaluation_summary` passa a contar a partir do **primeiro snapshot de preços** (antes dele os drops não têm valor
  em gemas e só diluíam a média).
- A cada snapshot, o `market_prices` grava `gems.potential`: as 10 melhores hunts da conta em gemas/h, qualquer que
  seja o foco. A página `/compensa` e a página da conta mostram isso.

## E. Painel

Métricas agrupadas por tema; plugins em JSON recolhidos em "Avançado"; previsão de objetivo acima de 5 anos vira "sem
previsão"; menu com a página atual; "Drops (gemas)/h" primeiro na visão geral; card "Gemas" na página da conta.

## F. Objetivo de teste

"Dratini teste" filtrava "Dratine"; corrigido para "Dratini" no banco.

## Testes

`worker/tests/test_gems.py` (modelo, liquidez entre contas, `PaceBook`/`rates_for`, `parse_loot_stones`,
`GameFilesSync`, plugin `gems` em ensaio e agindo, histerese, rank agindo, potencial),
`test_rank_plugin.py` (desvio de ritmo, estimativa pelo nível, puladas entre reinícios), `test_commands.py`
(`focus.set` gems) e o caso 8 do `supabase/tests/evaluation_test.sql` (janela a partir do primeiro preço).
