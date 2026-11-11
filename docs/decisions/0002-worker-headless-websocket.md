# 0002 — Worker headless via WebSocket (sem navegador)

- **Status:** Aceita
- **Data:** 2026-11-11

## Contexto

O jogo roda numa aba do navegador e conversa com o servidor por WebSocket. Projetos da comunidade (DiuleJR/pokeidle-manager-online, Romeu-q/ThoseIdles) mostram que dá para manter a sessão e mandar comandos sem navegador. Todos os sorteios acontecem no servidor, então o cliente só recebe e anima resultados.

## Decisão

O worker é um cliente WebSocket em Python (asyncio + `websockets`), com as mensagens modeladas em Pydantic. Nada de Playwright ou Puppeteer no caminho principal.

## Consequências

- Consumo baixo de RAM e CPU, o que permite um droplet pequeno (512 MB–1 GB).
- Depende de mapear o protocolo (fase 1), e uma mudança no protocolo pode quebrar o worker. Os modelos Pydantic devem falhar de forma explícita quando chegar uma mensagem desconhecida.
- A stack é a mesma de outros projetos (Python, Pydantic).

## Alternativas consideradas

- **Navegador headless (Playwright):** mais robusto a mudanças de UI, mas pesado (centenas de MB por conta) e mais frágil a mudanças de DOM. Fica como plano B se o protocolo for inviável.
- **Extensão ou userscript:** exige um navegador aberto 24/7 e não combina com o painel remoto.
