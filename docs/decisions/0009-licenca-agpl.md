# 0009 — Licença AGPL-3.0

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O repositório é público. Sem licença, ninguém poderia reaproveitar nada legalmente. A principal referência do projeto, o [DiuleJR/pokeidle-manager-online](https://github.com/DiuleJR/pokeidle-manager-online), é AGPL-3.0.

## Decisão

O projeto é licenciado sob a **GNU Affero General Public License v3.0** (arquivo [LICENSE](../../LICENSE)).

## Consequências

- Podemos reaproveitar código do DiuleJR/pokeidle-manager-online, que tem licença compatível, desde que **mantenhamos os avisos de copyright e indiquemos a origem** no arquivo e no README.
- Quem usar este código, inclusive como serviço acessado pela rede (é o "A" de Affero), precisa disponibilizar o código-fonte com as modificações sob a mesma licença.
- O painel na Vercel conta como serviço em rede, e o código dele já é público aqui, então não há conflito.

## Alternativas consideradas

- **MIT:** mais permissiva, mas impediria reaproveitar código AGPL.
- **Sem licença:** bloquearia qualquer reaproveitamento por terceiros.
