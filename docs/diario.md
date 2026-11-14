# Diário do projeto

Registro curto do que foi feito em cada dia, o que deu errado e o que ficou pendente.
As decisões em si ficam nos [ADRs](decisions/); aqui fica o caminho até elas.

## 2026-11-14

### Feito

- **Worker atualizado no PC de casa**: git com autor `Luiz Fernando <luizfsjunior@users.noreply.github.com>`,
  `WORKER_HOLDER=pc-casa` e `docker compose up -d --build`. Sessão `luizfsjunior_1` chegou a READY com
  `telemetry` e `restock`.
- **Fase 4b conferida de ponta a ponta** (painel → Supabase → worker em casa): Ping ("sessão ready em
  pc-casa"), Reconectar e `plugin.set` funcionaram.
- **Protocolo da 3b confirmado no navegador** (conta pessoal, Chrome com Claude in Chrome e um gravador de
  WebSocket na página que ignora o `hello`): `hunt.select` e `centro.ir`, o `trocaLivreEm` de 10 s, o
  Lançar até Capturar desligado pelo servidor na captura e o significado do `topCatchNova` (comparado com a tela
  do ranking: posição 101, 12 espécies). Detalhes em [protocolo.md](protocolo.md#observado-em-14112026-troca-de-hunt-e-lançar-até-capturar).

### Problemas e soluções

| Sintoma | Causa | Solução |
|---|---|---|
| Zen DevTools MCP: `Zen executable not found` | ele só procura o Zen no caminho do macOS; `--zen-path` com espaço quebra no `cmd /c` | `-e "ZEN_PATH=C:\Program Files\Zen Browser\zen.exe"` no `claude mcp add` |
| O MCP abre outro Zen, sem login | por padrão ele usa um perfil próprio em `~/.zen-devtools-mcp` | logar nesse perfil, ou `CONNECT_EXISTING=true` com o Zen aberto via `--marionette` |
| Em `CONNECT_EXISTING`, aba vazia e `Cannot read properties of undefined (reading 'replace')` | bug do zen-devtools-mcp 0.2.0 no modo connect-existing (e esse modo não tem eventos de rede) | desistimos do Zen; usamos o Chrome com Claude in Chrome |
| Links do Windows abrindo errado | `http`/`https` apontavam para um app que não existe mais | Configurações → Apps padrão → Zen → Definir padrão |

### Pendente

- Implementar a 3b (passos 2 em diante da [ordem de implementação](design/fase-3b-rank-semanal.md#8-ordem-de-implementação)),
  a partir de specs e testes.
- Ainda a ver no jogo: o erro de `hunt.select` durante a trava, `m`/`ini` do `estado.topCatch` e se o `welcome`
  traz o `topCatch` da semana.
- Limpar a DigitalOcean (droplet e *Actions secrets*).

## 2026-11-13

### Feito

- **Revisão do que veio de casa** (19 commits da noite de 12/11): testes e lint ok. Painel ajustado para o
  gold líquido (eixo do gráfico aceita negativo, "Gold líquido/h" no card).
- **`restock` mais seguro**: o teto de gasto por hora agora sobrevive a reinícios (lê os `restock.bought` da
  última hora) e compra confirmada depois do prazo conta no teto (`late_confirm_s`, sem recomprar o item).
- **Fase 4b, comandos**: migration `20261113010000_commands.sql` (tabela, RLS, claim atômico, expiração,
  recuperação, retenção), `Supervisor` e `CommandLoop` no worker (`ping`, ligar/desligar conta, reconectar,
  `plugin.set`), `listen --fake` para testar sem o jogo, e no painel os botões no card, `/comandos` e
  `/contas/<id>` com os plugins. Testes: SQL em Postgres local e 82 no worker.
- **Migrations automáticas**: integração GitHub do Supabase ligada (deploy para produção a cada push em
  `main`), com as migrations antigas registradas à mão no histórico ([deploy.md](deploy.md), seção 6).
  Testado: o push aplicou a de comandos (histórico termina em `commands` e a tabela existe).
- **Wiki do jogo**: as regras que importam para o worker (captura por estágio evolutivo, automações de bola,
  Top Catch, níveis das regiões, troca de área, Safari) resumidas em [regras-do-jogo.md](regras-do-jogo.md).
- **Fase 3b, rank semanal (desenho)**: [design/fase-3b-rank-semanal.md](design/fase-3b-rank-semanal.md).
  - Top Catch = espécies diferentes capturadas com bola na semana; vira sábado 23h59 (Brasília); paga
    50/20/5 💎 para 1º, 2º–10º e 11º–100º.
  - Catálogo do `welcome`: **1.043 hunts, uma espécie cada**, do nível 1 ao 160.300.
  - Estratégia (decidida): fila de hunts, da mais rápida para a mais lenta pelo tempo esperado até a captura;
    em cada uma, **Lançar até Capturar** (desliga na primeira captura) e, capturou, próxima hunt.
  - Bolas parametrizáveis: lista permitida + regra `se_paga` (padrão; Ultra quando o abate rende ≥ 130 de
    ouro) ou `fixa`, com teto semanal de gasto.
  - Foco por conta escolhido no painel (captura, ouro-xp-drop, rank).

### Problemas e soluções

| Sintoma | Causa | Solução |
|---|---|---|
| Commits aparecem como `unknown <gmail>` | git do PC de casa sem `user.name` e com o e-mail pessoal | `git config --global user.name/user.email` com o noreply do GitHub |
| `plugin desconhecido: restock` nos testes locais | pacote instalado antes do entry point do `restock` | reinstalar (`pip install -e './worker[dev]'`); no Docker o build já reinstala |
| Consulta do catálogo de hunts voltou só "1" | desde o tradutor v2 o `welcome` não grava as tabelas do jogo | ler de um `state.snapshot` antigo (`raw ? 'hunts'`); a 3b vai gravar o catálogo numa tabela própria |

### Próximos passos (em casa)

1. **Worker atualizado**
   - `git config --global user.name "Luiz Fernando"` e
     `git config --global user.email "luizfsjunior@users.noreply.github.com"`.
   - `WORKER_HOLDER=pc-casa` no `.env`.
   - `git pull` e `docker compose up -d --build`.
   - No painel: **Ping** no card (esperado: "feito — sessão ready em pc-casa"), depois **Reconectar** e um
     `plugin.set` pela página de Plugins.
2. **DevTools, conta pessoal** (aba Network → WS; não copiar o `hello`; fechar a aba sem clicar em "Sair"):
   - Trocar de hunt pelo Mapa: anotar a mensagem enviada e o que chega depois (`hunt.select`).
   - Lançar até Capturar ligado até uma captura: anotar o `estado` que chega em seguida (a `automation` volta
     com `autoBallAteCapturar: false`?) e o `topCatchNova` da captura.
3. **Implementar a 3b**, nesta ordem:
   - tabela do catálogo do jogo (hunts, `captura`, `catalogoBolas`), gravada só quando muda;
   - fila de hunts ordenada pelo tempo até a captura, com testes;
   - plugin `rank` em `observe_only` (grava `rank.plan` e o que faria) e o foco `rank` no `restock`;
   - seletor de foco e parâmetros do rank no painel;
   - depois de conferir alguns dias: ligar o `hunt.select` e o Lançar até Capturar de verdade.
4. **Pendências antigas**: apagar o droplet da DigitalOcean e os Actions secrets que sobraram.

## 2026-11-12

### Feito

- **Design e núcleo da fase 2**: sessão WebSocket, barramento de eventos, plugins, telemetria
  e a migration inicial (contas, tokens no Vault, leases, eventos, configs). Docker e guia de deploy.
- **DigitalOcean bloqueada**: o jogo respondeu `provedorBanido` para o IP do droplet.
  Virou o [ADR 0011](decisions/0011-worker-em-ip-residencial.md): o worker roda em IP residencial.
  Pedido formal enviado ao suporte perguntando sobre VPS/proxy. Sem autorização, nada de proxy, VPN ou túnel.
- **Simulador** (`pokeidle-farm simulate`): gera dias de eventos com os sorteios dos Termos, para
  desenvolver métricas e painel sem o jogo. Agora carimba `hunt_slug` em abates e capturas.
- **Codespaces**: devcontainer com Python 3.12 e Node, para trabalhar do PC do trabalho sem instalar nada.
  Só dev e simulador; o worker contra o jogo não roda lá (IP de datacenter).
- **Métricas em camadas** ([ADR 0012](decisions/0012-metricas-em-camadas.md)): `metric_hourly`,
  `metric_daily`, definições base e razão, `metric_series()`, objetivos com ritmo, previsão e chance
  (Poisson), fotos de hora em hora pelo pg_cron. Testado em Postgres local e no Supabase real:
  ~360 abates por hora ativa em todos os dias simulados.
- **Painel v1 no ar na Vercel** (`web/`): login por e-mail e senha, visão geral por conta, gráficos
  por hora e dia com filtro de conta e hunt, objetivos criados sem SQL com histórico.
- **Desenho da fase 4b** (comandos do painel para o worker): [design/fase-4b-comandos.md](design/fase-4b-comandos.md).
- **Primeira sessão real do worker** (à noite, no PC de casa, via Docker, `observe_only`): o IP residencial
  passou, o handshake funcionou com o token do Vault e os abates reais de Magikarp chegaram ao Supabase com
  `hunt_slug`. O que foi aprendido do protocolo está em [protocolo.md](protocolo.md#observado-na-sessão-real).
  Com a bola automática ligada vieram `bola` e `fugiu` reais; quando as bolas acabam, o jogo só para de jogar.
  O saldo de ouro confirmou que o `ouroLoot` já está dentro do `ouro`.
- **Spec do tradutor v2** ([design/tradutor-v2.md](design/tradutor-v2.md)): corrige o `estado` aninhado e
  o Centro tratado como hunt, e tira o ruído do banco. Implementado com os 14 casos de teste aprovados. A sessão
  passou a copiar a hunt atual do tradutor (antes só mudava com `hunt.changed`).
- **Primeira captura real** (Ultra Ball): o `capturado` virou `pokemon.captured` e as duas capturas gravadas
  no formato antigo foram convertidas no banco.
- **`shop.buy` e `auto.set` confirmados no DevTools** (pela conta pessoal) e preços da loja tirados de prints.
- **Fase 3a implementada** ([design/fase-3-reposicao.md](design/fase-3-reposicao.md)): plugin `restock`
  (escolha da melhor bola que se paga pelo ouro líquido, foco ouro-xp-drop, reposição de bolas, poções e
  revives), `item.consumed` e preço da bola nos eventos, métricas `consumables_gold`, `gold_net` e
  `gold_net_per_hour`.
- **Fase 3a ligada** (migration aplicada, `restock` na conta, `ACTION_MODE=enabled`): as primeiras ações reais
  do worker, um `auto.set` (Great Ball primeiro) e um `shop.buy` de 1.000 Great Balls, deram certo e foram
  confirmadas pelo `estado`. Antes, em `observe_only`, as decisões foram conferidas com os números reais.

### Problemas e soluções

| Sintoma | Causa | Solução |
|---|---|---|
| `REJECTED (provedorBanido)` no droplet | IP de datacenter barrado pelo jogo | ADR 0011: só IP residencial |
| pip: `requires a different Python: 3.14` no codespace | codespace criado antes do devcontainer | `git pull` + **Rebuild Container** |
| `pokeidle-farm: command not found` | terminal aberto antes da instalação | abrir terminal novo (ou `python -m pokeidle_farm.main`) |
| "Supabase não configurado", conta não encontrada | segredos criados em *Actions secrets* | criar em **Codespaces secrets** e reiniciar o codespace |
| `PGRST202 refresh_metric_hourly` | migration de métricas não aplicada | rodar `20261112010000_metrics.sql` |
| `relation "accounts" already exists` | migration inicial rodada de novo | cada migration roda uma vez só; aplicar só o arquivo novo |
| Painel sem conectar na Vercel | variáveis `NEXT_PUBLIC_` entram no build | colocar antes do deploy ou dar **Redeploy** depois |
| Card mostra "Rejeitada" | status que ficou da tentativa no droplet; o simulador não mexe em status | normal; o worker atualiza quando rodar em casa (confirmado: virou `ready`) |
| `dockerDesktopLinuxEngine: The system cannot find the file specified` | Docker Desktop fechado | abrir o Docker Desktop e esperar o engine subir |
| Worker caiu em `NEEDS_LOGIN (close 4001)` | conta aberta no navegador para trocar de hunt | esperado (sessão única). Fechar a aba sem "Sair" e `docker compose up -d`; o token continua valendo |
| Worker sai com `ValueError: 'enable' is not a valid ActionMode` | `ACTION_MODE=enable` no `.env` | o valor é `enabled` (com "d") |
| `pkMud` não aparece em `state.patch.pokemon_changed` | o patch real é aninhado (`estado.pkMud`); o tradutor procura no topo | corrigido no tradutor v2 |

### Pendente

- Apagar o droplet da DigitalOcean e os *Actions secrets* que sobraram.
- Esperar a resposta do suporte sobre VPS/proxy (ADR 0011).
- Fase 3a: confirmar os ids 203, 204 e 206.
- Fase 3b (rank semanal de espécies): desenhar.
- Ver uma captura real (para o `pokemon.captured`): a bola automática "sem parar" (exige VIP) já está
  ligada, mas as 100 Poké Balls acabaram sem captura (chance de 0,3% em Magikarp). Resolvido: com Ultra Balls veio a primeira captura, e o `capturado` virou
  `pokemon.captured` real.
- Fase 4b: implementar os comandos seguindo o desenho.
- Depois: fase 3 (`auto.set`), telemetria de captura vinda do `pkMud` (`pokemon.captured` ainda é
  provisório), retenção dos eventos brutos, métricas do Mercado.
