# Captura pelo painel: escolher a espécie (16/11/2026)

Pedido de 16/11: escolher no painel qual pokémon capturar. O fim pode ser depois de N capturas, depois
de um tempo, o que vier primeiro, ou só quando o usuário parar.

## Como funciona no jogo

A automação nativa (`estado.automation`) **não filtra por espécie**:
- `ballIds` é a ordem das bolas;
- `autoBallSemParar` liga a bola em todo selvagem;
- `autoBallAteCapturar` joga até capturar, e o servidor desliga essa flag a cada captura;
- `autoLockShiny` e `autoLockNotaMin` travam o pokémon depois de capturado, não escolhem quem capturar.

Mas cada hunt tem uma **espécie principal**. Por isso, "capturar o X" é ir para a hunt do X com a bola
ligada.

> **22/11/2026:** a bola automática exige VIP. O plugin não liga mais o "Lançar até Capturar": publica o alvo e o
> `ball_thrower` joga a bola à mão. Ver [captura-manual.md](captura-manual.md). O texto abaixo é o desenho original.

## Plugin `capture_target`

- **Config:** `species_id`, `hunt_slug`, `ball_id` (1 a 4), `count` (opcional), `until` (opcional) e
  `started_at`.
- **Travas no `ActionGateway`.** A trava genérica é `holds`: ação → (até, dono, rótulo). A trava de hunt
  da fase 3 virou um caso dela. Durante a captura, o plugin trava:
  - **`hunt.select`**: gems e rank esperam;
  - **`auto.set`**: o restock pula a sincronização das bolas, e o rank recebe `ActionBlocked` com
    `wait_s`.
- **Troca de hunt** pelo `HuntSwitcher`.
- **Bola:** liga o "Lançar até Capturar" com a bola escolhida na frente e **religa** sempre que o servidor
  desliga (a cada captura).
- **Repõe a bola** com ouro quando cai abaixo de 30: até 200, sem passar da reserva de 5 mil.
- **Conta** os `pokemon.captured` da espécie desde `started_at`, e a contagem sobrevive a uma reconexão.
- **Fim**, no que vier primeiro: `count` ou `until`. Sem os dois, só o `capture.stop` encerra.
  - Devolve as flags de bola e solta as travas, e os outros plugins voltam a decidir.
  - Grava `capture_target.ended` com o motivo (`count`, `expired`, `stopped`) e desliga a própria config.
  - Durante a captura, grava `capture_target.progress` a cada captura da espécie.

## Comandos

- **`capture.start`** `{species_id, species_name?, hunt_slug, ball_id, count?, hours?}` liga o plugin com
  `started_at` agora. Desliga o `hunt_hold`, se estiver ligado: a captura cuida da hunt.
- **`capture.stop`** desliga o plugin.
- A migration `20261116060000` amplia o check de tipos de comando.

## Painel

- **Pokédex:** o detalhe da espécie tem **Começar a captura**, com a hunt (quando há mais de uma), a bola
  (com o estoque) e o fim (N capturas, tempo, o que vier primeiro, ou só ao parar). Se já houver uma
  captura dessa espécie, mostra o progresso e **Parar a captura**.
- **Gaveta da hunt** (Hunts): o mesmo formulário, para a espécie da hunt.
- **Página da conta, aba Estratégia:** o card **Captura** mostra a captura em andamento e o progresso,
  contado pelos `pokemon.captured` desde o início.
