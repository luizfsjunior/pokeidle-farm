# Tradutor para a fase 3b: ranking, troca de hunt e Lançar até Capturar

Status: **rascunho** (14/11/2026), aguardando aprovação das decisões e dos casos de teste.

É o passo 2 da [ordem de implementação da 3b](fase-3b-rank-semanal.md#8-ordem-de-implementação). O formato
das mensagens foi confirmado no navegador em 14/11 ([protocolo.md](../protocolo.md#observado-em-14112026-troca-de-hunt-e-lançar-até-capturar)).
Mexe só em `worker/src/pokeidle_farm/events.py` (`Translator`) e nos testes de `worker/tests/test_protocol.py`.

## Problemas

| # | Problema | Efeito hoje |
|---|---|---|
| P1 | `topCatchNova` vira `battle.topCatchNova` sem `data` | plugin `rank` e métricas de ranking teriam que ler o `raw` |
| P2 | `hunt.changed` não traz o `trocaLivreEm` | o plugin não sabe quando pode mandar o próximo `hunt.select` |
| P3 | O Lançar até Capturar desligado pelo servidor só aparece como a `automation` inteira dentro de `state.patch` | o plugin teria que guardar a `automation` anterior e comparar |
| P4 | `estado.topCatch` (resumo da semana) é descartado do `data` | o número de espécies da semana não fica fácil de consultar |

## Proposta

### 1. `topCatchNova` → `rank.catch` (P1)

`batalha` `k: topCatchNova` vira `rank.catch`, **gravado** (no máximo algumas dezenas por semana por conta):

| Campo | Origem | Exemplo |
|---|---|---|
| `species_id` | `sp` | `10` |
| `week_start` | `s` (texto, como vem) | `"2026-11-08"` |
| `week_species` | `n` | `12` |
| `week_minute` | `m` (minutos desde o início da semana) | `9502` |
| `scores` | `pontua` | `true` |
| `hunt_slug` | hunt atual | `"caterpie"` |

`chave` não entra no `data` (é o `sp` em texto); continua no `raw`.

### 2. `hunt.changed` com `switch_free_at` (P2)

`hunt.changed.data` ganha `switch_free_at`: o `trocaLivreEm` (ms epoch) convertido para data e hora em UTC
(ISO), ou `null` se não vier. Hoje o `data` tem só `slug` e `name`.

### 3. Evento derivado `auto.catch_until_capture_off` (P3)

O `Translator` passa a guardar a última `automation` conhecida (do `welcome` e de cada `estado` que trouxer
`automation`). Quando um `estado` traz `autoBallAteCapturar: false` e a última conhecida era `true`, além do
`state.patch` sai um `auto.catch_until_capture_off` com `{hunt_slug}`, **gravado**.

- Sem `automation` conhecida antes (por exemplo, sem `welcome`): não emite.
- `false` → `false`, `true` → `true`, `false` → `true`: não emite.
- Desligar na mão (pelo painel ou por um `auto.set` do próprio worker) também emite. O plugin `rank` decide o
  que fazer com isso (ele sabe se foi ele quem desligou).

### 4. `topCatch` no `data` (P4)

- `PATCH_FIELDS` ganha `topCatch` → `top_catch` (o objeto como vem: `{s, n, m, ini}`).
- `state.snapshot.data` ganha `top_catch`: o `estado.topCatch` do `welcome`, ou `null` se não vier. Ainda não
  sabemos se o `welcome` traz isso; se trouxer, fica gravado sem mudar código.

### Fora deste passo

- `batalha` `k: aviso` (`hunt.ondaEspera`) continua `battle.aviso` sem `data`.
- O simulador não gera `rank.catch`; entra junto com as métricas de ranking (passo 6 da 3b).
- Ajuste no desenho da 3b, seção 4: a confirmação do `HuntSelect` passa a ser o `hunt.changed` (o `k: hunt`),
  não o `huntSlug` no `estado`, que nem sempre vem.

## Decisões a tomar

- **D1. Nome do evento do ranking:** `rank.catch` (proposto) ou outro.
- **D2. `auto.catch_until_capture_off` como evento derivado** (proposto) ou deixar o plugin comparar a
  `automation` por conta própria. Prefiro o evento: a comparação fica num lugar só e testada aqui.
- **D3. `week_start` como texto** (`"2026-11-08"`, proposto) ou como data e hora (domingo 00:00 de Brasília em
  UTC). O texto é o que o jogo manda e basta para agrupar por semana.

## Casos de teste propostos

Todos em `worker/tests/test_protocol.py`, com frames no formato real de 14/11.

1. **`topCatchNova` real:** numa hunt `caterpie`,
   `{"k":"topCatchNova","s":"2026-11-08","chave":"10","sp":10,"m":9502,"n":12,"pontua":true}` → um `rank.catch`
   com `data == {"species_id": 10, "week_start": "2026-11-08", "week_species": 12, "week_minute": 9502,
   "scores": True, "hunt_slug": "caterpie"}`. `rank.catch` fora de `NOT_PERSISTED`.
2. **`pontua: false`** → `scores is False`.
3. **`topCatchNova` vazio** (`{"k":"topCatchNova"}`) → `rank.catch` com todos os campos `None`, sem quebrar
   (`hunt_slug` continua o atual).
4. **Frame da captura** (`bola` com `sucesso: true` + `topCatchNova` na mesma `batalha`) → tipos
   `["capture_attempt", "rank.catch"]`, nessa ordem.
5. **`k: hunt` com `trocaLivreEm`:** `{"k":"hunt","slug":"meowth","nome":"Meowth","trocaLivreEm":1794676585909}`
   → `hunt.changed` com `data == {"slug": "meowth", "name": "Meowth", "switch_free_at":
   "2026-11-14T17:16:25.909000Z"}` (ou o formato ISO que o pydantic gerar em modo JSON). Os abates seguintes
   saem com `hunt_slug == "meowth"`.
6. **`k: hunt` sem `trocaLivreEm`** → `switch_free_at is None`.
7. **Lançar até Capturar desligado pelo servidor:** `welcome` com `automation.autoBallAteCapturar: true` numa
   hunt `caterpie`, depois `{"t":"estado","estado":{"automation":{..., "autoBallAteCapturar": false}}}` →
   `["state.patch", "auto.catch_until_capture_off"]`, o segundo com `data == {"hunt_slug": "caterpie"}`.
   `auto.catch_until_capture_off` fora de `NOT_PERSISTED`.
8. **Sem transição, sem evento:** `false` → `false`, `false` → `true` e um patch sem `automation` geram só o
   `state.patch`.
9. **Ligado por patch e desligado depois:** `welcome` com `false`, patch com `true` (sem evento), patch com
   `false` → emite (a `automation` conhecida acompanha os patches, não só o `welcome`).
10. **Sem `welcome`:** um patch com `autoBallAteCapturar: false` não emite (não se sabe o valor anterior).
11. **`topCatch` no patch:** `{"t":"estado","estado":{"topCatch":{"s":"2026-11-08","n":12,"m":12,"ini":false}}}`
    → `state.patch.data["top_catch"] == {"s": "2026-11-08", "n": 12, "m": 12, "ini": False}`.
12. **`topCatch` no `welcome`:** presente → `state.snapshot.data["top_catch"]` igual ao objeto; ausente → `None`.
13. **Os testes atuais continuam passando**, exceto os que comparam o `data` inteiro de `hunt.changed` ou do
    `state.snapshot`, que ganham `switch_free_at` e `top_catch`.
