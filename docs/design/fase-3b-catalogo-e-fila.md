# Fase 3b: catálogo de hunts e fila por tempo até a captura

Status: **rascunho** (14/11/2026), aguardando aprovação das decisões e dos casos de teste.

É o passo 3 da [ordem de implementação da 3b](fase-3b-rank-semanal.md#8-ordem-de-implementação). Entrega duas
peças que o plugin `rank` (passo 4) vai usar, sem nenhuma ação no jogo:

1. **Catálogo**: as hunts e as tabelas de captura do `welcome`, em memória no worker e numa tabela no Supabase.
2. **Fila**: uma função pura que recebe o catálogo e o que a conta já sabe e devolve as hunts em ordem de tempo
   esperado até a captura.

## O que o `welcome` traz (conferido em 14/11 no último `welcome` completo gravado, de 12/11)

- `hunts[]`: **1.043 hunts, uma espécie cada, e nenhuma espécie se repete entre hunts**. Então "espécie" e
  "hunt" são a mesma coisa para a fila, e não existe escolha entre hunts para a mesma espécie.
  ```json
  {"area": "orre", "regiao": "hoenn", "nome": "Treecko", "slug": "treecko_hoenn", "nivel": 500,
   "especies": [{"nome": "Treecko", "pokeId": 13252, "pontos": 16}], "totalSpawns": 16,
   "looktype": 60252, "pixel": [550, 50]}
  ```
  `area`: `kanto` (239, nível 1 a 470, inclui Johto), `outland` (58, nível 150) e `orre` (746, nível 500 a
  160.300, com `regiao` hoenn, sinnoh, unova, kalos, alola, galar e paldea). 271 hunts não têm `regiao`,
  `looktype` nem `pixel`.
- `captura`: `{"base": 0.0075, "piso": 0.003, "teto": 0.1, "porDegrau": {"20": 2.8669, "40": 3.5745,
  "100": 4.4681}, "raridadeDiv": 17, ...}`.
- `catalogoBolas`: `[{id, nome, catchRate, priceGold?, compravel}]` (Beast Ball sem `priceGold`).
- **Não traz o estágio evolutivo** das espécies das hunts (o `degrau` só aparece no catálogo de bosses), então
  a chance de captura de uma espécie só é conhecida de verdade depois da primeira bola nela: o `bola` traz a
  `chance`.
- `estado.topCatch` vem como `{"m": 0, "n": 0, "s": "2026-11-08", "ini": false}`: o número de espécies da
  semana, **sem a lista** de quais. As espécies da semana saem dos nossos `rank.catch` com `scores: true`.

## Proposta

### 1. Catálogo

**Em memória.** `HuntCatalog.from_welcome(raw) -> HuntCatalog`, com:

- `hunts: dict[slug, Hunt]`, sendo `Hunt(slug, name, area, region, level, species_id, species_name,
  total_spawns)`. `region` é `regiao` ou, sem ele, a `area`. Hunt sem espécie (`especies` vazio) fica fora.
- `capture: CaptureTable(base, floor, ceiling, by_step)` (de `captura`; `by_step` em ordem crescente de fator).
- `balls: dict[id, BallInfo(id, name, catch_rate, price)]` (de `catalogoBolas`; `price` `None` se não vier).
- `version`: hash estável (sha256 do JSON com chaves ordenadas) de `hunts`, `captura` e `catalogoBolas`.
- Nunca quebra: `welcome` sem essas chaves dá um catálogo vazio, e hunt malformada é ignorada.

A sessão guarda o catálogo do último `welcome` e o deixa disponível aos plugins (`ctx.catalog`).

**No Supabase.** Migration nova com:

- `game_hunts(slug pk, name, area, region, level, species_id, species_name, total_spawns, updated_at)`.
- `game_catalog(key pk, version, data jsonb, updated_at)`, com uma linha `hunts` (só a `version`), `captura` e
  `catalogoBolas` (o JSON como vem).
- RLS igual às outras tabelas de leitura do painel (leitura para logados, escrita só com a service role).

Gravação: no `welcome`, se a `version` for diferente da que a sessão já gravou nesta execução **e** da que está
em `game_catalog`, faz upsert das hunts e das tabelas. Hunts que sumiram do catálogo são apagadas. Como as
contas recebem o mesmo catálogo, na prática grava uma vez por mudança do jogo.

### 2. Fila (`plan_queue`)

Função pura, sem I/O:

```python
plan_queue(
    catalog: HuntCatalog,
    trainer_level: int,
    scored_species: set[int],          # rank.catch com scores=True na semana atual
    ball_id: int,                      # bola que vai ser usada (escolhida pelo restock/rank)
    kills_per_hour: dict[str, float],  # medido por hunt (slug); pode estar vazio
    default_kills_per_hour: float,     # ritmo da conta para hunts sem medida
    known_chance: dict[int, float],    # chance observada por espécie, já com a bola `ball_id`
) -> list[QueueItem]
```

`QueueItem(slug, species_id, name, level, kills_per_hour, chance, hours, chance_known, kph_known)`.

- **Alcançáveis**: `hunt.level <= trainer_level`.
- **Faltam**: `species_id` fora de `scored_species`.
- **Chance**: `known_chance[species_id]` se houver; senão a **pior** chance da tabela para a bola (estágio
  "última forma"): `clamp(base × catch_rate / max(by_step) × 1,4, floor, ceiling)`. Com a Ultra Ball, ~0,94%.
- **Abates/h**: `kills_per_hour[slug]` se houver; senão `default_kills_per_hour`.
- **Horas**: `1 / (abates/h × chance)` (uma espécie por hunt, então `P(spawn) = 1`).
- **Ordem**: `hours` crescente; empate por `level` crescente e depois `slug`.
- Bola desconhecida no catálogo, `default_kills_per_hour <= 0` ou nada alcançável: fila vazia.

### 3. Chance observada por espécie

`known_chance` sai dos `capture_attempt` (que têm `chance` e `ball_id`) cruzados com a espécie do abate. Hoje
o `capture_attempt` não traz a espécie, mas traz o `hunt_slug`, e cada hunt tem uma espécie só, então
`species_id = catalog.hunts[hunt_slug].species_id`. Para usar a chance de outra bola, converte pelo
`catch_rate`: `chance × catch_rate(nova) / catch_rate(observada)`, com o mesmo `clamp`. A função
`observed_chances(attempts, catalog, ball_id) -> dict[int, float]` fica junto da fila (pura, testada aqui); a
leitura dos eventos no banco fica para o plugin.

### Fora deste passo

- Ler os eventos do banco (`rank.catch` da semana, `capture_attempt`, abates/h por hunt): plugin `rank`, passo 4.
- Painel mostrando a fila: depois do passo 4 (o plugin grava `rank.plan`).

## Decisões a tomar

- **D1. Chance desconhecida:** usar a **pior** (última forma, proposto), a do meio, ou tentar a melhor para não
  deixar básicas para trás? A pior não põe à frente uma espécie lenta por engano; a primeira bola corrige.
- **D2. Abates/h de hunt nunca visitada:** o ritmo médio da conta (proposto; a wiki diz que todas as áreas têm o
  mesmo ritmo de ondas, e o que muda é a força do time), ou penalizar hunts de nível mais alto?
- **D3. Catálogo no Supabase** (proposto: `game_hunts` + `game_catalog`) ou só em memória por enquanto. A
  tabela serve para consultar e mostrar no painel sem depender do `welcome` gravado.
- **D4. Espécies da semana só pelos nossos `rank.catch`:** captura feita com o worker parado (ou na mão) não
  entra, e a espécie volta para a fila (custa uma captura repetida, não quebra nada). Vale procurar no
  navegador a mensagem do painel semanal da Pokedex ou do filtro "não capturados na semana" do Mapa?

## Casos de teste propostos

Catálogo (`worker/tests/test_catalog.py`, com um `welcome` de 4 ou 5 hunts no formato real):

1. **Hunt completa** (com `regiao`) → `Hunt(slug="treecko_hoenn", name="Treecko", area="orre", region="hoenn",
   level=500, species_id=13252, species_name="Treecko", total_spawns=16)`.
2. **Hunt sem `regiao`** (Caterpie, `kanto`) → `region == "kanto"`.
3. **Hunt sem espécie** (`especies: []`) fica fora; hunt malformada (sem `slug` ou `nivel` não numérico) também.
4. **`captura` e `catalogoBolas`** → `CaptureTable(0.0075, 0.003, 0.1, by_step=(2.8669, 3.5745, 4.4681))` e
   `balls[4] == BallInfo(4, "Ultra Ball", 4, 130)`; `balls[5].price is None`.
5. **`welcome` sem as tabelas** → catálogo vazio, sem exceção.
6. **`version` estável:** o mesmo conteúdo com as chaves em outra ordem dá a mesma `version`; mudar o `nivel`
   de uma hunt muda a `version`.
7. **Gravação só quando muda** (com `MemoryStore`): dois `welcome` iguais gravam uma vez; um `welcome` com uma
   hunt a menos regrava e apaga a que sumiu; uma `version` já presente no store não regrava ao reiniciar.

Fila (`worker/tests/test_rank_queue.py`):

8. **Alcance:** treinador nível 150 não vê hunt de nível 500; vê Kanto (1 a 150) e Outland (150).
9. **Espécie que já pontuou** sai da fila.
10. **Ordem por horas:** duas hunts com o mesmo abates/h, uma com `known_chance` 0,0146 e outra desconhecida
    (0,0094) → a conhecida vem primeiro; `hours` ≈ `1 / (1000 × 0,0146)` = 0,0685 com 1.000 abates/h.
11. **Abates/h medido** vence o padrão: hunt com 2.000/h medido passa à frente de uma igual com o padrão 1.000/h.
12. **Chance padrão por bola:** Poke Ball desconhecida = `max(0,0075 × 1 / 4,4681 × 1,4, 0,003)` = 0,003
    (piso); Ultra = 0,0075 × 4 / 4,4681 × 1,4 ≈ 0,0094.
13. **Desempate** por `level` e depois `slug`.
14. **Casos vazios:** bola fora do catálogo, `default_kills_per_hour = 0` ou nada alcançável → `[]`.
15. **`observed_chances`:** um `capture_attempt` com `chance 0.015`, `ball_id 4`, `hunt_slug "caterpie"` →
    `{10: 0.015}` para a Ultra; pedindo para a Great (catch_rate 2) → `{10: 0.0075}`; para a Poke →
    `{10: 0.00375}`; tentativa de hunt fora do catálogo ou sem `chance` é ignorada; com várias tentativas da
    mesma espécie vale a mais recente.
