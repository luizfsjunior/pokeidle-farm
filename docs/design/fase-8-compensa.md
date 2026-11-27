# Fase 8: "Compensa?" (avaliar a renda contra o custo)

Status: **implementado** (15/11/2026), decisões D-T a D-X tomadas (fim do documento). Código: migration
`20261115040000_evaluation.sql` (`evaluation_settings`, `evaluation_summary`, `evaluation_liquidity` e
`evaluation_constants` com a comissão e o preço da gema), página `web/app/compensa/` (`page.tsx` e
`SettingsForm.tsx`). Testes: casos 1 a 7 em `supabase/tests/evaluation_test.sql`.

Diferenças do texto abaixo para o que foi implementado:
- O custo de energia é da máquina, não de cada conta: as linhas por conta mostram só a renda; o custo e o lucro
  aparecem no total e na linha "com 3 contas" (a mesma máquina rodaria as três).
- A `window_days` fica na tabela, mas a página ainda não tem campo para mudá-la (o padrão é 7, como decidido).

É a fase 8 do [roadmap](../roadmap.md): com as métricas da fase 7, responder se o farm compensa. A fase pede 1 a 2
semanas de dados; a proposta é montar a conta **agora**, numa página que fica mais confiável sozinha conforme os
dias passam e que mostra quantos dias de dado sustentam cada número.

## A conta

Do roadmap, com o que já sabemos das regras:

```
renda_mensal_usd = gemas_dos_drops_por_mês × (1 − comissão) × 0,009
lucro_mensal_usd = renda_mensal_usd − custo_mensal_usd
```

- **Gemas dos drops**: a métrica `drops_value_orb` (fase 7): cada drop vale a média de 7 dias do Mercado em gemas.
  Pressupõe vender tudo pela média (ver liquidez, seção 3).
- **Comissão**: 15% em vendas de item em gemas (`TAXA_ORB_PLANA` do `shared/taxa-mercado.mjs` público, confirmado
  em 15/11; bate com o `regras-do-jogo.md`). As faixas de 13%/10%/7,5% só valem para pokémon, que não entram aqui.
- **US$ 0,009 por gema**: preço de recompra (saque) do jogo; saque mínimo de 1.000 gemas, com aprovação manual.
- **Ouro** não vira dólar (só as gemas saem do jogo); aparece como informação, não entra na renda.
- **Custo**: energia da máquina de casa e um custo fixo mensal em US$ (proxy, desde 16/11; parâmetros na
  seção 2). O Supabase e a Vercel estão no plano grátis.

## Proposta

### 1. Projeção por mês (D-T, D-U)

Para cada conta e para o total, numa janela dos últimos `N` dias (padrão 7):

| Número | Conta |
|---|---|
| Gemas na janela | Σ `drops_value_orb` |
| Horas ativas na janela | Σ `active_minutes` ÷ 60 |
| Gemas por dia corrido | gemas ÷ dias da janela com dado (do primeiro abate da conta na janela até agora) |
| Gemas por hora ativa | gemas ÷ horas ativas |
| **Projeção do mês (como está)** | gemas por dia corrido × 30 (inclui o tempo com o worker parado) |
| Projeção do mês (24 h/dia) | gemas por hora ativa × 24 × 30 (o teto, com o worker sempre ligado) |
| Renda, custo e lucro em US$ | a conta acima, para as duas projeções |
| Dias de dado | quantos dias da janela têm abates; com menos de 7, a página avisa que a projeção ainda é fraca |

E uma linha "com 3 contas", multiplicando a média por conta por 3 (a fase 5 ainda não rodou; é só uma estimativa).

### 2. Parâmetros de custo (D-V)

Tabela nova `evaluation_settings` (uma linha por dono, editável na página, RLS como as outras):

| Campo | Padrão | Uso |
|---|---|---|
| `machine_watts` | vazio | consumo médio da máquina que roda o worker |
| `marginal` | `false` | `true`: a máquina ficaria ligada de qualquer jeito, então o custo de energia do farm é 0 |
| `kwh_price_brl` | vazio | tarifa de energia (R$/kWh, vem na conta de luz) |
| `usd_brl` | vazio | câmbio para converter o custo em dólar |
| `window_days` | `7` | janela da projeção |
| `fixed_cost_usd` | vazio | custo fixo por mês em US$: proxy (migration `20261116070000`) |

```
energia = marginal ? 0 : machine_watts / 1000 × 24 × 30 × kwh_price_brl ÷ usd_brl
custo_mensal_usd = energia + fixed_cost_usd   (o que estiver vazio conta 0)
```

O custo só é **desconhecido** quando a energia não dá para calcular (`marginal = false` e algum dos três campos vazio)
**e** o fixo está vazio: a função devolve `cost_usd` nulo, o lucro é calculado sem o custo e a página mostra "custo do
mês não informado" ao lado do veredito, com os campos para preencher. O worker 24/7: `marginal = true` (o PC de
casa não entra) e o fixo com o proxy (~US$ 10 em 16/11).

### 3. Liquidez (D-W)

Vender tudo pela média só é realista se o volume das contas for pequeno perto do que o Mercado vende. Para cada item
dropado na janela: unidades dropadas por semana ÷ unidades vendidas por semana no Mercado (`units` do último
`market_prices` em gemas). Acima de `10%`, a página marca o item: a projeção dele é otimista.

### 4. Onde fica

- **Função no banco** `evaluation_summary(p_days int)` (`security invoker`, lê só as contas do dono pelo RLS): devolve
  uma linha por conta e uma de total com os números da seção 1. A página só formata. Testável no Postgres local.
- **Página `/compensa`**: o veredito no topo ("compensa: US$ X por mês de lucro" / "não compensa" / "dados
  insuficientes"), a tabela por conta, os parâmetros editáveis e a lista de liquidez. Link no menu.

## Fora desta fase

- Renda de pokémon capturados e dos prêmios do Top Catch (diamantes): sem preço simples por enquanto.
- Vender de verdade (fase 9). A conta aqui supõe que tudo se vende pela média.

## Decisões (tomadas em 15/11)

- **D-T. Base da projeção**: as duas, dias corridos ("como está") e 24 h/dia.
- **D-U. Janela**: 7 dias.
- **D-V. Custo de energia**: sem valores conhecidos. Os campos começam vazios e a página avisa que o lucro está
  sem o custo até serem preenchidos. Em 15/11 gravamos uma **estimativa** na conta do dono: 100 W em média
  (PC de mesa ligado 24 h, quase ocioso), R$ 0,85/kWh (média residencial com impostos) e R$ 5,50 por US$, o que dá
  ~US$ 11,13 por mês. Trocar pelo formulário da página quando houver números reais.
- **D-W. Liquidez**: marcar acima de 10% das unidades vendidas na semana.
- **D-X. Veredito**: "compensa" quando o lucro mensal projetado (como está) for maior que 0; com o custo
  desconhecido, o veredito vem com a ressalva. Com menos de 7 dias de dado: "dados insuficientes".

## Casos de teste propostos

SQL (`supabase/tests/evaluation_test.sql`), com uma conta, `metric_hourly` montado à mão e `evaluation_settings`:

1. 7 dias com 100 gemas por dia e 12 h ativas por dia → gemas por dia corrido 100, por hora ativa 8,33, projeção
   do mês 3.000 (como está) e 6.000 (24 h/dia).
2. Renda: 3.000 gemas × 0,85 × 0,009 = US$ 22,95.
3. Custo: 60 W, R$ 0,90/kWh, câmbio 5,0 → 60/1000 × 720 × 0,90 ÷ 5 = US$ 7,78; lucro US$ 15,17. Com
   `marginal = true` → custo 0. Sem a tarifa (campo vazio) e `marginal = false` → `cost_usd` nulo e lucro = renda
   (US$ 22,95). Sem linha em `evaluation_settings` → igual ao caso sem tarifa.
4. Conta com abates só nos últimos 3 dias → dias de dado 3 e gemas por dia corrido sobre 3 dias, não 7.
5. Duas contas → linha de total com a soma; linha "com 3 contas" = média por conta × 3.
6. RLS: outro usuário não vê as contas nem os parâmetros do dono.
7. Liquidez: 20 unidades dropadas na semana de um item com 100 vendidas → 20%, marcado; com 1.000 → 2%, não.

Painel: `npm run typecheck`, build e conferência no navegador.
