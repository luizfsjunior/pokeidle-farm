# Tradutor v2: eventos no formato real do jogo

Status: **decisões aprovadas** (12/11/2026); falta aprovar os casos de teste antes de implementar.

Motivo: na primeira sessão real (12/11/2026, ver [protocolo.md](../protocolo.md#observado-na-sessão-real))
o tradutor de `worker/src/pokeidle_farm/events.py` mostrou dois bugs, gravou muito ruído e não gerou
captura real.

## Problemas

| # | Problema | Efeito hoje |
|---|---|---|
| P1 | O `estado` real é aninhado (`{t, estado: {pkMud, huntSlug, ...}}`), mas o tradutor lê `pkMud`, `pkFora` e `huntSlug` no topo | `pokemon_changed` sempre vazio; troca de hunt por patch passa despercebida |
| P2 | `campo.init` do Centro vem com `slug: "centro"`, e o tradutor guarda isso como hunt | abate logo depois do Centro seria gravado com `hunt_slug = "centro"` |
| P3 | `state.patch` grava o `estado` duas vezes (em `data.changed` e em `raw`), com o `pkMud` completo, a cada abate | ~1.000 linhas grandes por hora por conta |
| P4 | `campo` (~3/s na hunt, ~6 MB/h), `chat` (~45/min, mensagens de terceiros) e `vivo` são gravados como `unknown` | a maior parte do volume da tabela `events` é ruído |
| P5 | O `welcome` (~450 KB) é gravado inteiro a cada conexão, incluindo as tabelas do jogo (hunts, mercado, catálogos) | cada reconexão grava ~450 KB |
| P6 | `morte` real traz `ouroLoot`, `lootBoost` e `xpPokemon`, que o tradutor descarta | informação perdida |
| P7 | `shiny.captura` (anúncio global de outros jogadores), `spawn` e `levelup` caem em `unknown` ou `battle.*` sem dados | difícil de consultar |
| P8 | O worker real nunca emite `pokemon.captured`, que as métricas usam para capturas, shinies e objetivos | captura real sempre zerada no painel |

## Proposta

### 1. `estado` aninhado (P1)

- Ler `pkMud`, `pkFora` e `huntSlug` de `raw["estado"]`.
- Aceitar também o formato antigo (no topo), já que o código atual e os testes usam esse formato e não custa nada.
- `huntSlug` presente e não vazio atualiza a hunt atual.

### 2. `campo.init` do Centro (P2)

- Se `centro` for verdadeiro **ou** `slug == "centro"`, a hunt atual **não muda**.
- `field.init` passa a carregar `{slug, map, is_center}` (`map` vem de `mapa`).

### 3. `state.patch` enxuto (P3)

- `data` guarda só os escalares úteis que vierem no patch: `xp`, `gold`, `level`, `balls`, `hunt_slug` e `centro_livre_em`.
- `pokemon_changed` passa a ser a **lista de ids** (não o objeto inteiro); `pokemon_removed` continua uma lista de ids.
- O `raw` continua com o `estado` inteiro (fonte da verdade), sem duplicar em `data`.

### 4. Ruído fora do banco (P4)

Esses tipos são traduzidos e **passam pelo barramento** (um plugin pode querer usar depois), mas entram em `NOT_PERSISTED`:

| Mensagem | Tipo interno |
|---|---|
| `campo` | `field.tick` |
| `vivo` | `keepalive` |
| `chat`, `chat.del`, `chat.fixada` | `chat` |

`amigos` e `pvp` continuam `unknown` e gravados (chegam uma vez por conexão).

### 5. `welcome` enxuto (P5)

- O `raw` do `state.snapshot` guarda só `{t, estado}`. As tabelas do jogo (`hunts`, `mercado`, `catalogoBolas`, `captura` etc.) não são gravadas.
- `data` ganha `balls` e `automation`, além do que já tem.

### 6. `morte` completa (P6)

`kill.data` passa a ter:

| Campo | Origem | Notas |
|---|---|---|
| `xp` | `xpTreinador`, senão `xp` | igual a hoje |
| `xp_pokemon` | `xpPokemon` | novo |
| `gold` | `ouro` | igual a hoje |
| `gold_loot` | `ouroLoot` | novo. É uma **parte** do `ouro`, não um valor a mais (ver D4); não entra na métrica de ouro |
| `loot_boost` | `lootBoost` | novo |
| `gold_autosell`, `drops`, `wild_name`, `hunt_slug` | como hoje | |

### 7. Eventos novos (P7)

| Mensagem | Tipo interno | `data` | Gravado? |
|---|---|---|---|
| `batalha` `k: spawn` | `wild.spawned` | `{name, level, max_hp, species_id}` | não (D2) |
| `batalha` `k: levelup` | `level_up` | `{who, level}` (`who` vem de `quem`) | sim |
| `batalha` `k: fugiu` | `wild_fled` | `{name, level, shiny}` (ganha `shiny`) | sim |
| `shiny.captura` | `global.shiny_captured` | `{nick, species, level, species_id}` | sim (D3) |

### 8. Captura real (P8): fica para depois

A captura real ainda não foi vista (chance de 0,3% por bola em Magikarp). O formato provável é `bola`
com `sucesso: true`, seguido de um pokémon novo no `estado.pkMud`. Sem ver isso acontecer, não dá para
escrever o teste. **Fora do escopo desta entrega.** Quando aparecer uma captura no banco, vira uma
entrega pequena: gerar `pokemon.captured` com `species`, `level`, `shiny`, `potency`, `quality`, `ivs`
e `iv_sum`, no formato que o simulador e as métricas já usam.

## Decisões (aprovadas em 12/11/2026)

- **D1. Ruído:** traduzir e passar pelo barramento, mas **não gravar** (`NOT_PERSISTED`).
- **D2. `wild.spawned`:** **não gravar** (~1.000 por hora por conta, pouco valor por enquanto).
- **D3. `global.shiny_captured`:** **gravar**. É público, pequeno e raro, e dá um feed de shinies do servidor.
- **D4. Métrica de ouro:** continua `gold + gold_autosell`, sem `gold_loot`. Confirmado com dados: em
  288 abates seguidos o saldo do `estado.gold` subiu exatamente o `ouro` (41) de cada `morte`, então
  o `ouroLoot` (5) já está dentro do `ouro`. Somar contaria em dobro.

## Casos de teste propostos

Todos em `worker/tests/test_protocol.py`, com frames no **formato real** observado.

1. **Patch aninhado:** `{"t":"estado","estado":{"xp":165,"gold":1115,"pkMud":[{"id":7,...}],"pkFora":[3]}}`
   → `state.patch` com `data == {"xp":165, "gold":1115, "pokemon_changed":[7], "pokemon_removed":[3]}`.
2. **Formato antigo continua funcionando:** `{"t":"estado","pkMud":[{"id":7}]}` → `pokemon_changed == [7]`.
3. **Hunt pelo patch:** `{"t":"estado","estado":{"huntSlug":"caverna"}}` e depois `morte` → `kill.data.hunt_slug == "caverna"`.
4. **Centro não é hunt:** welcome com `huntSlug: "magikarp"`, depois `campo.init` com `slug: "centro", centro: true`, depois `morte` → `hunt_slug == "magikarp"`; o `field.init` tem `is_center: true`.
5. **`campo.init` de hunt troca a hunt:** `campo.init` com `slug: "caverna"` → abates seguintes com `hunt_slug == "caverna"`.
6. **`morte` real:** o frame do protocolo (`xp:8, xpPokemon:11, xpTreinador:11, ouro:41, ouroLoot:5, lootBoost:true`)
   → `xp == 11`, `xp_pokemon == 11`, `gold == 41`, `gold_loot == 5`, `loot_boost is True`, `gold_autosell == 0`.
7. **Ruído traduzido mas não gravado:** `campo`, `vivo`, `chat`, `chat.del` e `chat.fixada` viram `field.tick`, `keepalive` e `chat`, e esses três tipos estão em `NOT_PERSISTED`.
8. **`amigos` continua `unknown`** e fora de `NOT_PERSISTED`.
9. **`welcome` enxuto:** um welcome com `hunts` e `mercado` → o `raw` do `state.snapshot` tem só as chaves `t` e `estado`; `data` tem `balls` e `automation`.
10. **`levelup`** `{"k":"levelup","quem":"treinador","level":3}` → `level_up` com `{who:"treinador", level:3}`.
11. **`fugiu`** com `shiny: false` → `wild_fled.data.shiny is False`.
12. **`spawn`** → `wild.spawned` com `{name, level, max_hp, species_id}`, e `wild.spawned` está em `NOT_PERSISTED`.
13. **`shiny.captura`** → `global.shiny_captured` com `{nick:"Elija", species:"Larvitar", level:20, species_id:246}`, fora de `NOT_PERSISTED`; **nunca** gera `pokemon.captured` nem `capture_attempt`.
14. **Os testes atuais continuam passando** (`test_translate_kill_and_capture`, `test_kills_carry_current_hunt` etc.), exceto onde o formato de `state.patch.data` muda de propósito.
