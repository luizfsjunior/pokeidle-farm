# Simulador, camada 3: sorte da captura

Status: **implementado** (16/11/2026), como biblioteca (`worker/src/pokeidle_farm/model/capture.py`); quem decide
capturar ou não é a camada 4. Base: as camadas 1 ([combate](simulador-1-combate.md)) e 2
([progressão](simulador-2-progressao.md)).

## Pergunta que responde

"Quanto tempo e ouro custa capturar a espécie X, e com que probabilidade o nascimento sai melhor que o meu ativo numa
hunt de referência, no mesmo nível?"

## Regras do jogo usadas (código público v1.420.0)

- **Uma bola por corpo**: cada abate deixa o corpo 30 s no chão e a automação joga 1 bola; capturas/h = abates/h ×
  chance.
- **Chance** = base (0,75%) × catchRate da bola ÷ fator do degrau da cadeia × 1,4, entre o piso (0,3%) e o teto (10%).
  Fatores (`captura-degrau.mjs`, também no `welcome.captura.porDegrau`): primeiro de três (teto de captura 20) 2,8669,
  meio (40) 3,5745, último ou sem evolução (100) 4,4681. É a `CaptureTable` do catálogo, a mesma que o rank já usa.
- **Nascimento** (`nota-pokemon.mjs`): três sorteios independentes que nunca mudam (evoluir não rerola):
  IV de 1 a 32 em cada stat; qualidade pelas faixas (0,8 a 1,8, com o buraco 1,6–1,7); potência P1 74,5%, P2 20%,
  P3 5%, P4 0,5%, P5 0,005% (+0/5/10/25/100%); shiny 1 em 24 mil (×3 nos stats).
- **Nível**: em Kanto o capturado nasce no nível da hunt.

## O modelo

- `roll_birth`: sorteia um nascimento pelas tabelas.
- `outcome(espécie, nível, hunt de referência, ritmo do ativo)`: Monte Carlo de `n_births` nascimentos, cada um na
  forma da cadeia daquele nível (`form_at_level`, evoluindo assim que pode) e simulado na hunt de referência (camada
  1). Devolve os quantis de abates/h (p10, p50, p90, p99) e `p_beats`, a fração que rende mais que o ativo.
- `CaptureOdds` e `CaptureOption`: abates, horas e ouro por captura; capturas, horas e ouro até um nascimento que
  vença o ativo (`1 / p_beats` capturas).

## Validação (16/11, conta de teste)

| | modelo | jogo |
|---|---|---|
| chance com Great Ball, cadeia de 3 (Poliwag, Weedle...) | 0,73% | o servidor mostra 0,7% |
| chance com Super Ball, cadeia de 3 (Horsea, Nidoran) | 1,10% | 1,1% |
| capturas por tentativa (1.000 tentativas) | ~0,7% | ~7 capturas |
| qualidade média | 1,176 | 1,142 (26 capturas) |
| IV médio por stat | 16,5 | 16,7 |
| potência P1 / P2 / P3 | 74 / 20 / 5% | 69 / 23 / 8% |

## Primeiro resultado: capturar não acelera a ida ao 150

Comparando no nível 60, na hunt da Onix, com o Ivysaur da conta (inicial: qualidade 1,6, IV 27, P2): **280
abates/h**. De todas as espécies das hunts de Kanto até o nível 40 (cada uma já evoluída no 60), só o Vileplume vence,
e em 6,7% dos nascimentos; todas as outras perdem sempre (a mediana da melhor fica em 226/h). O inicial nasce com
qualidade 1,6 e IV 27 fixos, o que um nascimento sorteado quase nunca alcança (qualidade ≥ 1,6 sai em ~1%).

Consequência para o protocolo: até o 150 o caminho é o inicial e as evoluções dele (como a camada 2 já faz). A captura
vale pelo que rende no Mercado (shiny, P4/P5, raros) e, depois do 150, pela Outland; isso entra na camada 4.

## Testes

`tests/test_capture_model.py`: chance igual à do servidor, distribuição dos nascimentos, multiplicador de potência e
shiny, forma pela cadeia, custos por captura e até vencer o ativo.
