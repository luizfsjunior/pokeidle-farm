# Simulador, camada 1: combate (abates por hora)

Status: **rascunho**, 15/11/2026. Decisões S-A a S-D em aberto (fim do documento).

## Objetivo do simulador

Montar o protocolo mais rápido para uma conta nova chegar ao **treinador nível 150** com um time capaz de farmar a
Outland 1, usando **só o que a conta ganha jogando**, tudo automático (VIP opcional), otimizando o **menor tempo até o
marco**. O simulador é também o "cérebro" do agente orquestrador futuro: o agente chama o simulador como ferramenta e
escolhe entre opções já calculadas.

Camadas, cada uma validada contra a conta de teste (`luizfsjunior_1`) antes da seguinte:

1. **Combate** (este documento): abates/h de um pokémon numa hunt.
2. Progressão: hora a hora, XP, níveis, hunts e ativo.
3. Sorte da captura: Monte Carlo de IV, qualidade, potência e shiny.
4. Decisões: hunt, ativo, o que capturar e comprar.
5. Protocolo: regras que o worker segue em contas novas.

## Regras do jogo usadas (código público, v1.420.0)

Os módulos `/shared/*.mjs` que o cliente importa são as regras do servidor (107 baixados em 15/11; vão para
`game_files` como a wiki).

- **Dano** (wiki, Combate): base = ((2 × nível/5 + 2) × poder × atk/def)/50 + 2; final = base × STAB (1,5 se o golpe é
  de um tipo do pokémon) × efetividade × aleatório(0,85–1,00). Físico usa Atk/Def; especial, Sp.Atk/Sp.Def.
- **Golpes**: por espécie em `golpes-planilhas.mjs` (poder, tipo, categoria, nível em que libera). Recarga
  (`cooldown-golpes.mjs`): 10 s a 30 s entre 15 e 100 de poder, 30 s a 60 s entre 100 e 600; o Speed base desconta até
  7%, proporcional ao IV de SPD. A cada ataque o pokémon usa o golpe pronto de maior dano esperado; com tudo em recarga,
  a **Investida** (poder 30, física, no tipo do pokémon, a cada 2 s, −10 ms por ponto de IV de SPD).
- **Stats** (wiki, Stats): stat = arred((base + 2·IV) × nível/100 × qualidade^expoente × multiplicador); expoente 0,95
  para HP e Velocidade, 0,8 para os outros; multiplicador de potência, ×3 shiny, lendário.
- **HP de combate** = máx(24, arred(hp × 12)); o **selvagem tem ×5**.
- **Efetividade**: tabela de tipos do jogo, "amplificada" (`tipo-efetividade.mjs` + a tabela que o servidor manda).
- **Inicial**: qualidade 1,6 e IV 27 em tudo (`starter.mjs`). Um pokémon só luta até 5 níveis acima do treinador
  (`pokemon-nivel-treinador.mjs`; o inicial é exceção).

## O modelo

```
tempo por abate = tempo de deslocamento + HP do selvagem ÷ dano por segundo do ativo
abates/h = 3600 ÷ tempo por abate
```

- **Dano por segundo**: simula a sequência de ataques (golpes por prioridade de dano, recargas, Investida) contra o
  selvagem daquela hunt, com o dano médio (aleatório 0,925).
- **Selvagem**: espécie da hunt, nível = nível da hunt, stats com IV e qualidade médios (S-B).
- **Deslocamento**: constante calibrada pelo teto medido (~1.100 abates/h → ~3,3 s por abate quando o dano é alto).

## Validação (o que decide se a camada está pronta)

Com os abates gravados desde 15/11 (nível do ativo em cada abate): para cada hunt × nível do ativo com 30+ abates,
comparar os abates/h medidos com os previstos. Critério: **erro mediano ≤ 25%** e a **ordem** das hunts
preservada (a melhor hunt prevista é a melhor medida). Pontos já conhecidos (Bulbasaur 16–23): Horsea ~600/h,
Magikarp e Geodude ~1.000–1.100/h (teto), Nidoran e Zubat ~100/h, Charmander e Bulbasaur ~60/h.

## Entregas

- `worker/src/pokeidle_farm/sim/combat.py` (puro, sem rede): `kills_per_hour(attacker, hunt, catalog) -> float`.
- Carga das regras: golpes e base stats das espécies (dos `creatures*.json` e `golpes-planilhas.mjs`), tabela de
  efetividade.
- Script de validação contra os eventos da conta, com a tabela previsto × medido.
- Uso imediato: escolher o **pokémon ativo** pela hunt (o de mais abates/h previstos entre os da conta).

## Decisões em aberto

- **S-A. Onde rodar**: no worker (Python, perto dos dados e das ações) — proposta — ou num serviço à parte?
- **S-B. Selvagem**: IV médio (16,5) e qualidade 1,0, ou tirar a distribuição do jogo (`captura-degrau`/qualidade)?
- **S-C. Deslocamento**: uma constante calibrada (proposta) ou modelar a onda de spawn do mapa?
- **S-D. Fonte dos golpes**: portar a leitura de `golpes-planilhas.mjs` (JavaScript) para Python (proposta), ou tirar
  dos `creatures*.json` (o campo `attacks` que hoje descartamos)?

## Casos de teste propostos

1. Fórmula de dano: um golpe conhecido, nível, stats e efetividade → o dano exato da wiki.
2. Recarga: poder 15 → 10 s, 100 → 30 s, 600 → 60 s; desconto do Speed com IV 32 e 16.
3. Stats: espécie, nível, IV e qualidade → os stats que o jogo mostra para o Bulbasaur da conta (nível 23, IV 27,
   qualidade 1,6: atk 36, spAtk 42...).
4. Teto: dano altíssimo → abates/h = 3600 ÷ deslocamento.
5. Validação: tabela previsto × medido das hunts da conta dentro do critério.
