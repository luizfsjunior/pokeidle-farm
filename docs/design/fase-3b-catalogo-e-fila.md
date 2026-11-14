# Fase 3b: catálogo de hunts, Pokedex e fila por tempo até a captura

Status: **aprovado** (14/11/2026), decisões D1 a D6 tomadas.

É o passo 3 da [ordem de implementação da 3b](fase-3b-rank-semanal.md#8-ordem-de-implementação). Entrega as
peças que o plugin `rank` (passo 4) vai usar. A única mensagem nova para o jogo é um pedido de leitura
(`topcatch.pedir`); nenhuma ação muda o estado da conta.

## Fontes (conferidas em 14/11)

| O quê | De onde | Observação |
|---|---|---|
| Hunts, tabela de captura, bolas | `welcome`: `hunts[]`, `captura`, `catalogoBolas` | 1.043 hunts, **uma espécie cada, sem espécie repetida entre hunts** |
| Pokedex (estágio evolutivo etc.) | arquivos públicos `https://pokeidle.io/assets/creatures.json`, `creatures-novos.json`, `creatures-outland-novos.json`, `creatures-formas.json` | o `welcome` não traz o estágio; os quatro juntos cobrem as 1.043 espécies |
| Espécies que já pontuaram na semana | `topcatch.pedir` → `topCatch` com `e: [[chave, minuto], ...]` | o `welcome` e o `estado` só trazem a contagem |

Hunt real:
```json
{"area": "orre", "regiao": "hoenn", "nome": "Treecko", "slug": "treecko_hoenn", "nivel": 500,
 "especies": [{"nome": "Treecko", "pokeId": 13252, "pontos": 16}], "totalSpawns": 16,
 "looktype": 60252, "pixel": [550, 50]}
```
`area`: `kanto` (239, nível 1 a 470, inclui Johto), `outland` (58, nível 150) e `orre` (746, nível 500 a 160.300,
com `regiao` hoenn a paldea). 271 hunts não têm `regiao`, `looktype` nem `pixel`.

Espécie real (`creatures.json`, sem `loot` e `attacks`):
```json
{"pokeId": 10, "name": "Caterpie", "type1": "BUG", "rarity": "COMMON", "huntLevel": 1,
 "evolvesToId": 11, "evolveLevel": 10, "priceNpc": 80, "experience": 8, "baseHp": 45, ...}
```

`captura`: `{"base": 0.0075, "piso": 0.003, "teto": 0.1, "porDegrau": {"20": 2.8669, "40": 3.5745, "100": 4.4681}}`.
Os três fatores são, em ordem, os da wiki para "1º de três", "meio ou 1º de dois" e "última ou não evolui".

## Proposta

### 1. Catálogo de hunts

`HuntCatalog.from_welcome(raw) -> HuntCatalog`:

- `hunts: dict[slug, Hunt]`, sendo `Hunt(slug, name, area, region, level, species_id, species_name,
  total_spawns)`. `region` é `regiao` ou, sem ele, a `area`. Hunt sem espécie ou malformada fica fora.
- `capture: CaptureTable(base, floor, ceiling, by_step)`, com `by_step` em ordem crescente.
- `balls: dict[id, BallInfo(id, name, catch_rate, price)]` (`price` `None` se não vier).
- `version`: sha256 do JSON com chaves ordenadas de `hunts`, `captura` e `catalogoBolas`.
- Nunca quebra: sem essas chaves, catálogo vazio.

A sessão guarda o catálogo do último `welcome` e o expõe aos plugins (`ctx.catalog`).

### 2. Pokedex

`SpeciesCatalog.from_creatures(files: list[dict]) -> SpeciesCatalog`, puro:

- Junta o `creatures` dos quatro arquivos, nesta ordem; se um `pokeId` repetir, vale o primeiro.
- `species: dict[id, Species(id, name, type1, type2, rarity, hunt_level, evolves_to, evolve_level, stage)]`.
- **`stage`** pela cadeia `evolvesToId` (só conta elo para espécie que existe no catálogo; protegido contra
  ciclo): cadeia de 3 ou mais e a espécie é a primeira → `first_of_three`; é a última da cadeia ou não evolui →
  `last`; senão → `middle`. Fator: `by_step[0]`, `by_step[1]` e `by_step[2]`, respectivamente.
- `version`: sha256 do conteúdo, como no catálogo de hunts.

Busca (`SpeciesSync`, D5): o worker confere os quatro arquivos por HTTP **na subida e a cada 24 h**, com GET
condicional: manda o `If-None-Match` com o `ETag` guardado (o servidor responde `ETag` fraco, como
`W/"10a9cb-1a09bb53ff0"`, e `max-age=14400`). `304` em todos → nada muda. Algum `200` → remonta o
`SpeciesCatalog` com os quatro arquivos e grava. Os `ETag`s ficam no `data` da linha `species` de
`game_catalog`. Assim a Pokedex se atualiza sozinha quando o jogo atualiza, sem baixar ~230 KB todo dia. Se
falhar, registra `species.fetch_failed` e segue com a última Pokedex gravada (ou sem ela: a fila usa a chance
pior, seção 5). Uma busca só por worker, não por conta.

### 3. Espécies da semana

- **Ação nova `TopCatchRequest`** → `{"t":"topcatch.pedir"}`, pelo `ActionGateway`, intervalo mínimo de 5 min.
  Quem manda é o plugin `rank` (passo 4), na subida e a cada reconexão.
- **Tradutor:** a mensagem `topCatch` vira `rank.week`, gravado, com `data`:
  `{week_start: s, week_species: n, species: {"10": 9502, "66": 8630, ...}}` (de `e`; chave como texto, como
  vem). `campeoes`, `ant` e `meu` ficam só no `raw`.
- Espécies da semana = as de `rank.week` mais as de `rank.catch` com `scores: true` que chegaram depois, desde
  que o `week_start` seja o da semana atual.

### 4. Supabase

Migration nova, com RLS de leitura para logados e escrita só com a service role:

- `game_hunts(slug pk, name, area, region, level, species_id, species_name, total_spawns, updated_at)`.
- `game_species(species_id pk, name, type1, type2, rarity, hunt_level, evolves_to, evolve_level, stage, data
  jsonb, updated_at)`, com `data` = a espécie como vem, sem `loot` e `attacks`.
- `game_catalog(key pk, version, data jsonb, updated_at)`: linhas `hunts`, `species` (só a `version`),
  `captura` e `catalogoBolas` (o JSON como vem).

Grava só quando a `version` muda (comparando com a que a sessão já gravou e com a de `game_catalog`). O que
sumiu do catálogo é apagado.

### 5. Fila (`plan_queue`)

Função pura:

```python
plan_queue(
    hunts: HuntCatalog,
    species: SpeciesCatalog | None,    # None se a Pokedex não carregou
    trainer_level: int,
    scored_species: set[int],
    ball_id: int,
    kills_per_hour: dict[str, float],  # medido por hunt (slug)
    default_kills_per_hour: float,     # ritmo médio da conta
    known_chance: dict[int, float],    # chance observada por espécie, já com a bola `ball_id`
) -> list[QueueItem]
```

`QueueItem(slug, species_id, name, level, kills_per_hour, chance, hours, chance_source, kph_known)`, com
`chance_source` em `observed`, `stage` ou `worst`.

- **Alcançáveis**: `hunt.level <= trainer_level`. **Faltam**: `species_id` fora de `scored_species`.
- **Chance** (decidido, D1): a observada, se houver; senão a do estágio pela Pokedex:
  `clamp(base × catch_rate / fator × 1,4, floor, ceiling)`; sem Pokedex ou espécie fora dela, a pior (fator
  `by_step[-1]`).
- **Abates/h** (decidido, D2): o medido na hunt, se houver; senão `default_kills_per_hour`.
- **Horas**: `1 / (abates/h × chance)`. **Ordem**: `hours` crescente; empate por `level` e depois `slug`.
- Bola fora do catálogo, `default_kills_per_hour <= 0` ou nada alcançável: fila vazia.

### 6. Chance observada (`observed_chances`)

`observed_chances(attempts, hunts, ball_id) -> dict[int, float]`, puro: cada `capture_attempt` com `chance`
vira a chance da espécie da hunt (`hunts[hunt_slug].species_id`), convertida para `ball_id` por
`chance × catch_rate(nova) / catch_rate(usada)`, com o mesmo `clamp`. Vale a tentativa mais recente.

### Fora deste passo

- Ler eventos do banco (`rank.week`, `rank.catch`, `capture_attempt`, abates por hunt) e mandar o
  `topcatch.pedir`: plugin `rank`, passo 4.
- Painel mostrando fila e Pokedex.
- Ideia para refinar D2 depois: o "Hunt Analyser" do Mapa estima XP/h e ouro/h por hunt com os boosts da conta
  (`/hunt-analyser.mjs`); dividido pelo XP por abate, daria abates/h de hunts nunca visitadas.

## Decisões

**Tomadas em 14/11:**

- **D1.** Chance de espécie nunca tentada: pelo estágio da Pokedex; a pior só sem Pokedex.
- **D2.** Abates/h de hunt nunca visitada: o ritmo médio da conta.
- **D3.** Catálogo e Pokedex no Supabase.
- **D4.** Espécies da semana pelo `topcatch.pedir` (achado no código do jogo), mais os `rank.catch`.

- **D5.** Pokedex atualizada sozinha quando o jogo atualizar: GET condicional por `ETag` na subida e a cada 24 h.
- **D6.** `topcatch.pedir` pelo `ActionGateway`, respeitando o `ACTION_MODE`. Em `observe_only` a fila só conhece
  as espécies dos `rank.catch`.

## Casos de teste propostos

Catálogo de hunts (`worker/tests/test_catalog.py`, `welcome` com 4 ou 5 hunts no formato real):

1. **Hunt completa** → `Hunt(slug="treecko_hoenn", name="Treecko", area="orre", region="hoenn", level=500,
   species_id=13252, species_name="Treecko", total_spawns=16)`.
2. **Sem `regiao`** (Caterpie, `kanto`) → `region == "kanto"`.
3. **Sem espécie** (`especies: []`) ou malformada (sem `slug`, `nivel` não numérico) → fora.
4. **Tabelas** → `CaptureTable(0.0075, 0.003, 0.1, (2.8669, 3.5745, 4.4681))`;
   `balls[4] == BallInfo(4, "Ultra Ball", 4, 130)`; `balls[5].price is None`.
5. **`welcome` sem as tabelas** → catálogo vazio, sem exceção.
6. **`version`**: chaves em outra ordem → mesma; `nivel` diferente → outra.

Pokedex (`worker/tests/test_species.py`, com recortes reais dos arquivos):

7. **Estágios**: Caterpie (10 → 11 → 12) = `first_of_three`; Metapod (11) = `middle`; Butterfree (12) = `last`;
   Magikarp (129 → 130) = `middle`; Gyarados (130) = `last`; Tauros (128, sem `evolvesToId`) = `last`.
8. **Elo para espécie que não existe** (`evolvesToId: 99999`) → tratada como sem evolução (`last`).
9. **Ciclo** (A → B → A) → não trava; as duas ficam `middle`.
10. **Arquivos juntos**: espécie em `creatures-novos` (com `_leia`) entra; `pokeId` repetido vale o do primeiro
    arquivo; arquivo sem `creatures` é ignorado.

Gravação (`MemoryStore`):

11. Dois `welcome` iguais gravam uma vez; um `welcome` com uma hunt a menos regrava e apaga a que sumiu; uma
    `version` já no store não regrava ao reiniciar. O mesmo para a Pokedex.
12. **Busca da Pokedex** com HTTP falso: a primeira busca manda GET sem `If-None-Match` e grava os `ETag`s; a
    segunda manda `If-None-Match` com eles e, com `304` em todos, não regrava; com `200` em um só, remonta com os
    quatro (os outros vêm do que já estava gravado ou de um GET sem condição) e grava; erro HTTP ou JSON inválido
    gera `species.fetch_failed`, mantém a Pokedex anterior e não levanta exceção.

Semana (`worker/tests/test_protocol.py` e `test_bus_actions.py`):

13. **`topCatch` real** (`e: [["10",9502],["66",8630]]`, `n: 12`, `s: "2026-11-08"`) → `rank.week` com
    `data == {"week_start": "2026-11-08", "week_species": 12, "species": {"10": 9502, "66": 8630}}`, fora de
    `NOT_PERSISTED`. `topCatch` sem `e` → `species == {}`.
14. **`TopCatchRequest`** → wire `{"t":"topcatch.pedir"}`; em `observe_only` não é enviado; dois pedidos em menos de 5 min → o segundo é barrado pelo rate limiter.

Fila (`worker/tests/test_rank_queue.py`):

15. **Alcance**: treinador nível 150 não vê hunt de nível 500; vê Kanto (até 150) e Outland (150).
16. **Espécie que já pontuou** sai da fila.
17. **Chance pelo estágio**: Ultra Ball, sem observação: Caterpie (`first_of_three`) = 0,0075 × 4 / 2,8669 × 1,4
    ≈ 0,01465 e `chance_source == "stage"`; Gyarados (`last`) ≈ 0,0094. Com 1.000 abates/h, Caterpie dá
    `hours` ≈ 0,0683 e vem antes.
18. **Sem Pokedex** (`species=None`) → todas com a pior chance e `chance_source == "worst"`. **Poke Ball** na
    pior → 0,0075 / 4,4681 × 1,4 ≈ 0,00235 → piso 0,003.
19. **Observada vence o estágio** (`known_chance` 0,02 → `chance_source == "observed"`).
20. **Abates/h medido** vence o padrão (2.000/h passa à frente de uma igual com 1.000/h).
21. **Desempate** por `level` e depois `slug`; **casos vazios** (bola fora do catálogo, padrão 0, nada
    alcançável) → `[]`.
22. **`observed_chances`**: `chance 0.015`, `ball_id 4`, `hunt_slug "caterpie"` → `{10: 0.015}` para a Ultra;
    `{10: 0.0075}` para a Great; `{10: 0.00375}` para a Poke; hunt fora do catálogo ou sem `chance` ignorada;
    várias tentativas da mesma espécie → a mais recente.
