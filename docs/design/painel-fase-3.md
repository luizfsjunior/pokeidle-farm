# Painel, fase 3: interações (16/11/2026)

## Escolher a hunt (`hunt.select` / `hunt.release`)

- **Comando `hunt.select {slug, hours}`** (0,25 a 24 h; padrão 2). Grava a config do plugin `hunt_hold`
  (`{slug, until}`), liga o plugin e o aplica na hora (`restart_plugin`). A trava sobrevive a uma
  reconexão, porque o prazo fica na config.
- **Plugin `hunt_hold`.** Troca de hunt pelo `HuntSwitcher`, com as mesmas regras do foco gemas: trava de
  combate, `trocaLivreEm`, confirmação pelo `hunt.changed` e nova tentativa. Também trava a hunt no
  `ActionGateway` até o prazo.
- **Trava no gateway.** Enquanto ela vale, um `hunt.select` de outra fonte (gems, rank) é bloqueado com
  `reason: "hunt_hold"` e `wait_s` até o fim do prazo. Os plugins já tratam `ActionBlocked` com `wait_s`,
  então esperam e voltam a escolher depois, sem código novo neles.
- **Fim da trava.** No fim do prazo, o plugin solta a trava e grava `hunt_hold.ended` (`reason:
  "expired"`). **`hunt.release`** desliga o plugin e solta na hora (`reason: "stopped"`).
- **No painel:**
  - a página da conta ganha o card **Hunt**: a hunt atual, a trava (hunt e prazo), a lista de hunts
    (por padrão só as até o nível do pokémon ativo + 5), o prazo e os botões;
  - na Pokédex, cada hunt onde a espécie aparece ganha o botão "Ir por 2 h".

## Ainda nesta fase (dependem do protocolo)

- **Trocar o pokémon ativo.** A mensagem ainda não é conhecida. A lista das mensagens do cliente sai do
  `app.js` gravado em `game_files`.
- **Evoluir pelo painel.** A ação `pokemon.evoluir` já existe (plugin gems) e falta o comando.
