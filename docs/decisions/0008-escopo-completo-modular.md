# 0008 — Escopo completo, com arquitetura modular

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

Havia três escopos possíveis para o worker:
- **A. Mínimo:** manter as contas conectadas, configurar a automação nativa (`auto.set`) e coletar métricas.
- **B. Intermediário:** o A, mais trocar para a melhor hunt, repor itens na loja e jogar bolas.
- **C. Completo:** o B, mais compra e venda no Mercado.

Além disso, o objetivo é calcular **métricas complexas, com objetivos específicos ao longo do tempo** (por exemplo: chegar a um nível até uma data, juntar N unidades de um item, atingir X Gemas por semana). Essas métricas vão mudar com o tempo.

## Decisão

O escopo é o **completo (C)**, construído por etapas e com tudo **plugável**:

1. **Estratégias como plugins.** Cada comportamento (hunt, restock, captura, venda, sniper) é um módulo independente, com uma interface comum, ligado e configurado por conta pelo painel.
2. **Barramento de eventos interno.** A sessão publica eventos tipados (abate, drop, captura, mudança de estado, resposta do Mercado). Estratégias e telemetria assinam esse barramento, sem depender umas das outras.
3. **Métricas em camadas:**
   - **Eventos brutos** (imutáveis), a fonte da verdade
   - **Agregados** por janela de tempo (hora, dia), recalculáveis a partir dos brutos
   - **Métricas derivadas** declaradas como definições (nome, fórmula e janela), não espalhadas pelo código
   - **Objetivos** (`goals`): uma meta sobre uma métrica (valor-alvo e prazo), com progresso, ritmo atual e previsão de conclusão
4. **Ordem de construção:** mesmo com escopo completo, a entrega segue A → B → C. Cada etapa só entra quando a anterior estiver estável e medida.

## Consequências

- Uma estratégia nova não mexe no núcleo, só registra um plugin.
- Uma métrica nova é uma definição a mais, sem precisar mudar o worker.
- Como os eventos brutos são guardados, dá para recalcular métricas antigas quando uma definição mudar.
- Mais trabalho no começo (interfaces e barramento) em troca de menos retrabalho depois.
- As estratégias de Mercado (C) seguem as regras de [regras-do-jogo.md](../regras-do-jogo.md): respeitar a retenção de 2 min e o sorteio, ter orçamento diário, nunca comprar de si mesmo e nunca usar preço combinado entre contas de pessoas diferentes.

## Alternativas consideradas

- **Escopo A ou B:** mais simples, mas não atendem ao objetivo de operar o Mercado.
- **Métricas codificadas direto no worker:** mais rápido de começar, mas cada métrica nova exigiria deploy e não daria para recalcular o histórico.
