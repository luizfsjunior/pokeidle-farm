# Diário do projeto

Registro curto do que foi feito em cada dia, o que deu errado e o que ficou pendente.
As decisões em si ficam nos [ADRs](decisions/); aqui fica o caminho até elas.

## 2026-11-16

### Feito

- **Worker 24/7 sem máquina em casa** ([ADR 0013](decisions/0013-vps-com-proxy-autorizado.md), revisa a 0011): o
  suporte, pelo Discord, não libera IP de servidor mas liberou proxy ou VPN. O worker ganhou `GAME_PROXY_URL` (só o
  tráfego do jogo: WebSocket e downloads da Pokedex/itens; o Supabase vai direto; HTTP ou SOCKS5) e a conferência do
  IP de saída no ipapi.is antes de conectar (`EXIT_IP_CHECK`): IP de datacenter não conecta. Guia em
  [deploy.md](deploy.md), seção 3b. 293 testes passando.

### Pendente

- Guardar o print da conversa com o suporte (fora do repo).
- VPS e proxy (escolhidos em 16/11): VM ARM grátis da **Oracle Cloud em São Paulo** (região principal permanente;
  se der "Out of capacity", tentar outro horário; Hetzner ou o droplet de US$ 4 como alternativa) e **IPRoyal ISP,
  Dedicated, Brasil, 1 proxy, 30 dias, fraud score Premium (IP Quality Score)**, ~US$ 5,40/mês, sem extras.
  Nas primeiras 24 h (reembolso), no VPS:
  `curl -s -x http://usuario:senha@host:porta https://api.ipapi.is/ | grep -E '"is_datacenter"|"is_abuser"|"type"|"name"'`
  → esperado `is_datacenter: false`, `is_abuser: false`, tipo `isp`. Se não, reembolso ou troca. Depois, guia da
  seção 3b do deploy.md (`WORKER_HOLDER=vps-1`, `GAME_PROXY_URL`), parar o worker de casa e conferir o Ping.
- `/compensa`: campo de custo fixo mensal (VPS + proxy), hoje só há energia.
- Lint: dois B008 em `model/combat.py` (de 15/11).

## 2026-11-15

### Feito

- **Ensaio do `rank` religado**: o worker tinha saído de forma limpa às 17:06 de 14/11 (Docker fechado; o
  `restart: on-failure` não religa nesse caso). Na subida, já na semana nova (`2026-11-15`): 0 espécies, 32 hunts
  na fila, alvo Bellsprout em ~8 min.
- **Trava de combate medida**: nos `state.patch`, o `centroLivreEm` fica de 2,4 s a 5 s à frente do relógio do
  servidor depois de cada golpe; dá para trocar de hunt entre um golpe e outro, sem ir ao Centro.
- **Passo 5 da 3b** ([fase-3b-rank-ligado.md](design/fase-3b-rank-ligado.md), decisões D-E a D-J): o `rank`
  agindo de verdade (troca de hunt respeitando a trava e o `trocaLivreEm`, confirmação pelo `hunt.changed`,
  nova tentativa, teto de 10 trocas por hora, Lançar até Capturar religado em toda captura, `rank.mode`),
  `restock` com `focus: "rank"` e `fallback_focus`, comando `focus.set` e o card **Foco** na página da conta.
  O padrão do `restock.focus` passou a ser `gold_xp_drop`. 179 testes, os testes SQL e o build do web passando.
- **Foco rank ligado em `luizfsjunior_1`** (17:07, pelo card **Foco**): Bellsprout → Caterpie → Geodude → Oddish,
  4 espécies na semana em ~10 min, cada troca confirmada pelo `hunt.changed` e o Lançar até Capturar religado.
- **Timer da trava de combate**: depois da primeira captura, a troca levou 2 min. O golpe que fecha a janela livre
  chega no mesmo frame que renova o `centroLivreEm`, então conferir a trava só a cada evento quase nunca a vê
  aberta. Agora o plugin agenda um timer para o fim da trava; as trocas seguintes saíram em ~1 s.
- **Posição no Top Catch achada no `app.js` do jogo**: o cliente pede `ranking.pedir` aba `capturas` (top 100) e
  calcula a posição sozinho (`tcPosicaoCom`); o `topCatch` não traz a posição.
- **Passo 6 da 3b** ([fase-3b-metricas-e-card.md](design/fase-3b-metricas-e-card.md), D-K a D-N): métrica
  `rank_points` (migration `20261115020000_rank_points.sql`), `ranking.pedir` → `rank.board` → `rank.position`,
  `min_active_minutes` 5, card "Rank semanal" na página da conta e a linha do rank na visão geral. 188 testes, os
  testes SQL e o build do web passando.
- **Posição conferida no painel**: 5 espécies, fora do top 100 (corte em 24). Dois detalhes corrigidos: o
  `ranking.pedir` barrado pelo limite de 5 min agora sai sozinho depois, e o card mostra a hunt do último
  `hunt.changed`.
- **Fase 7** ([fase-7-precos-do-mercado.md](design/fase-7-precos-do-mercado.md), D-O a D-S): pelo `app.js`, o
  `market.medias` traz a média de 7 dias de venda por item em gemas e ouro, e o `items.json` público liga o nome do
  drop ao id. Implementados: drops com quantidade, catálogo de itens por ETag, plugin `market_prices` (a cada
  hora, numa conta só), métricas `drops_value_orb`/`drops_value_gold`/`drops_unpriced` com o preço da hora de cada
  drop (sem vendas em ouro, o preço do NPC) e a página `/mercado`. 198 testes, os testes SQL e o build do web
  passando.
- **Fase 7 no ar**: a resposta real do `market.medias` bateu com o `app.js` (36 itens; Water Stone a 29 gemas ou
  ~129 mil de ouro). Nos 7 dias, ~435 gemas em drops. Os drops de antes do primeiro snapshot ficam pelo preço do
  NPC (decidido: as métricas valem daqui para a frente).
- **Fase 8** ([fase-8-compensa.md](design/fase-8-compensa.md), D-T a D-X): página `/compensa` com a renda mensal
  projetada (como está e 24 h/dia), custo de energia, lucro, veredito e liquidez, calculados por
  `evaluation_summary`/`evaluation_liquidity` no banco. Comissão de 15% confirmada no `shared/taxa-mercado.mjs`
  público. Testes SQL e build do web passando. Custo de energia estimado (100 W, R$ 0,85/kWh, R$ 5,50/US$):
  ~US$ 11 por mês. Os primeiros números (US$ 1,68/mês como está) são baixos porque só há preço em gemas desde
  15/11 15:51; o veredito sai de "dados insuficientes" por volta de 22/11.
- **Eventos do simulador apagados** da `luizfsjunior_1`: 34.441 eventos com `raw._sim = true` (09/11 a 12/11),
  com as métricas recalculadas desde 12/11.

### Problemas e soluções

| Problema | Causa | Solução |
|---|---|---|
| Worker parado desde 14/11 17:06 | Docker fechado; o `restart: on-failure` não religa uma saída limpa | `docker compose up -d --build`; depois, `restart: unless-stopped` no compose (volta sozinho com o Docker, desde que o Docker Desktop abra com o Windows) |
| Drops reais "sem preço" depois do deploy da fase 7 | a migration recalculou as métricas antes de o worker gravar o catálogo de itens | `refresh_metric_hourly('2026-11-12', now())` depois do `Itens: saved` |
| `vmmemWSL` ocupando muita RAM | WSL sem limite (até metade da RAM) e sem devolver o cache dos builds e testes | `%UserProfile%\.wslconfig` com `memory=2GB` e `autoMemoryReclaim=gradual`, depois `wsl --shutdown` (o Docker Desktop avisa "WSL distro terminated abruptly"; o engine volta sozinho) |
| Troca de hunt demorando 2 min numa hunt em que o selvagem ataca | o golpe que fecha a janela renova a trava no mesmo frame; o plugin só conferia a trava em eventos | timer para o fim da trava (`_schedule`/`_wake` no `rank`) |
| A conta parou de jogar bola depois do rebuild | o padrão novo do `restock.focus` (`gold_xp_drop`) com a config antiga sem `focus` | foco gravado pelo card **Foco** logo depois (esperado) |

- **`hunt.select` na trava é ignorado em silêncio** (18:50:46, logo depois de uma reconexão, trava 2,2 s à
  frente): sem `erro` nem `hunt.changed`; o plugin registrou `rank.failed` por timeout e a nova tentativa passou.
- **Ritmo por hunt medido** (nível 19): ~1.000/h em Magikarp e ~900/h em Poliwag, Weedle e Oddish, contra
  ~60–115/h em Nidoran, Zubat e Bulbasaur. A fila do rank já usa o ritmo medido.
- **Análise e melhorias** ([analise-2026-11-15.md](analise-2026-11-15.md), [foco-gemas-e-ritmo.md](design/foco-gemas-e-ritmo.md)):
  o modelo de captura bate (7 capturas contra 7,1 previstas); o problema do rank era o ritmo das hunts não medidas.
  Achado no código do jogo: toda hunt dropa a pedra do tipo a 0,2/0,35/0,5% por abate, e as pedras valem 8 a 142
  gemas. Implementados direto: ritmo aprendido no rank, foco gemas, wiki e fórmulas no banco, "Compensa?" a partir do
  primeiro preço com o potencial por hunt, ajustes no painel e o objetivo "Dratini" corrigido. 214 testes.
- **Sonda do Mercado** (plugin `seller`): anunciou 1 Water Stone a 999 gemas e cancelou (estoque 15 → 14 → 15).
  Protocolo de `market.item`/`criar`/`meus`/`cancelar` no [protocolo.md](protocolo.md). **Achado grave:** os 60
  anúncios abertos de Water Stone (4.607 unidades) estão todos a **2 gemas**, o mínimo do Mercado; a "média de 7 dias"
  do `market.medias` (~30) não é o preço de venda de hoje. As estimativas de gemas/h e US$/mês do foco gemas e do
  `/compensa` estão infladas e precisam usar o menor anúncio e a fila de cada pedra.
- **Progressão e Mercado** ([analise-progressao-e-mercado.md](analise-progressao-e-mercado.md)): vendas reais (Key Fragment
  ~222 gemas, 28 em 6 min; Mega Shiny Stone Fragment ~538), shiny anunciados a 35–175 mil gemas; fragmentos só na
  Outland (nível 150). Curva de XP e dano tiradas da wiki; XP/h real por hunt (Horsea 68 mil/h, 3,5× o Geodude); o time
  é só o Bulbasaur 23 com quatro Magikarps nível 1. Protocolo para contas novas: ~50 h de farm até o 150.
- **Foco XP** ([design/foco-xp.md](design/foco-xp.md)): plugin `gems` com `objective: "xp"`, XP/h = ritmo projetado
  × XP por abate (medida ou fórmula com o bônus da conta); "XP (subir de nível)" no card Foco. 237 testes.
- **Ritmo por nível do ativo** ([design/ritmo-por-nivel.md](design/ritmo-por-nivel.md)): abates com o nível do ativo,
  ritmo projetado pelo fator de dano. 234 testes; aguardando deploy.
- **Todas as pedras estão a 2 gemas** (primeira leitura completa, 22:07 UTC): 17 pedras, filas de centenas a 45 mil
  unidades, inclusive a Thunder (média 145). O `seller` em ensaio guarda tudo (piso de 85% da média).
- **Preço real das pedras e venda em ensaio** ([fase-9-venda-de-pedras.md](design/fase-9-venda-de-pedras.md)):
  `market_asks` de hora em hora, valor em gemas = o menor entre a média e o menor anúncio (modelo, métricas recalculadas
  e painéis), e o `seller` completo (guarda 5, alvo 1 abaixo do menor anúncio, piso de 85% da média) em `dry_run`.
- **Painel de hunts** (`/hunts`): visitadas por período e conta (função `hunt_summary`) e o catálogo alcançável com
  as pedras e "gemas por 1.000 abates".
- **Foco gemas virou o padrão** e `luizfsjunior_1` passou para ele (20:51 UTC, Geodude, ~47 gemas/h estimadas); o rank
  fica desligado, com a config guardada.
- **Roadmap organizado**: fases 1 a 4 concluídas, fase 5 com o Docker em casa pronto e faltando as contas.

### Pendente

- Deploy do ritmo por nível (`a1b80aa`) e da varredura.
- Foco XP e equipar o ativo pela hunt (`team.active`).
- Filtro de pokémon no histórico global de vendas.
- Conferir os `seller.plan` em ensaio e decidir se liga a venda de verdade (`dry_run: false`).
- Equipar o melhor time para a hunt (`team.active`/`team.move`).
- Fase 5: cadastrar as outras duas contas de farm (nick, token e dispositivo) e rodar as três juntas.
- Fase 8: veredito do `/compensa` por volta de 22/11 (7 dias de preços); trocar a estimativa de energia se houver
  números reais.
- Ainda não chegou um `sessao.renovada` (renovação do token) para conferir o formato.

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

- **Tradutor da 3b** ([tradutor-3b.md](design/tradutor-3b.md)): `rank.catch` (do `topCatchNova`),
  `hunt.changed.switch_free_at`, `auto.catch_until_capture_off` e `top_catch`.
- **Pokedex e semana do Top Catch achadas no jogo**: o estágio evolutivo vem dos `creatures*.json` públicos
  (`evolvesToId`), que cobrem as 1.043 hunts; a lista das espécies da semana vem do `topcatch.pedir`.
- **Passo 3 da 3b** ([fase-3b-catalogo-e-fila.md](design/fase-3b-catalogo-e-fila.md)): catálogo de hunts,
  Pokedex com `ETag`, `TopCatchRequest`/`rank.week`, fila por tempo até a captura e a migration
  `20261114010000_game_catalog.sql`. 125 testes; conferido com a Pokedex real e a migration num Postgres local.
- **Passo 4 da 3b** ([fase-3b-plugin-rank.md](design/fase-3b-plugin-rank.md)): plugin `rank` em ensaio, com
  `dry_run` próprio porque o `ACTION_MODE` já está em `enabled` pelo `restock`. Grava `rank.plan` e `rank.would`;
  replaneja na captura, na virada da semana, ao subir de nível, ao trocar de bola e por tempo na hunt alvo
  (histerese de 10% para trocar de hunt). Super Ball incluída nas bolas padrão (`[4, 3, 2, 1]`). Ação
  `HuntSelect` e a função `rank_hunt_stats` no banco. 150 testes e o teste SQL novo passando.
- **Ensaio do `rank` ligado** em `luizfsjunior_1` (worker em casa, config `{}`): a migration `rank_hunt_stats`
  foi aplicada pelo push; o `topcatch.pedir` voltou com 1 espécie na semana (Magikarp); nível 16, 31 hunts na
  fila, Great Ball, chance de 0,73% no 1º de três estágios, 1.007 abates/h (o medido no Magikarp) e alvo
  Bellsprout em ~8 min. Os `rank.would` (`hunt.select` e `auto.set`) foram gravados e nada saiu para o jogo.

### Problemas e soluções

| Sintoma | Causa | Solução |
|---|---|---|
| `pytest` não roda no PC (só Python 3.13) | o projeto exige 3.12 | testes no Docker (`python:3.12-slim`, comando no README do worker) |
| Zen DevTools MCP: `Zen executable not found` | ele só procura o Zen no caminho do macOS; `--zen-path` com espaço quebra no `cmd /c` | `-e "ZEN_PATH=C:\Program Files\Zen Browser\zen.exe"` no `claude mcp add` |
| O MCP abre outro Zen, sem login | por padrão ele usa um perfil próprio em `~/.zen-devtools-mcp` | logar nesse perfil, ou `CONNECT_EXISTING=true` com o Zen aberto via `--marionette` |
| Em `CONNECT_EXISTING`, aba vazia e `Cannot read properties of undefined (reading 'replace')` | bug do zen-devtools-mcp 0.2.0 no modo connect-existing (e esse modo não tem eventos de rede) | desistimos do Zen; usamos o Chrome com Claude in Chrome |
| Ritmo padrão do `rank` em ~390/h, contra ~1.000/h no Magikarp | eventos do simulador (hunts `sim-*`, ~360/h) gravados na conta real entravam na média | o `rank` só conta hunts que existem no catálogo |
| Plugin `rank` aparecia duas vezes no painel depois de salvar | o editor do "Adicionar plugin" ficava aberto enquanto o `AutoRefresh` trazia o plugin do banco para a lista (no banco havia uma linha só) | o editor fecha quando o plugin aparece na lista |
| Links do Windows abrindo errado | `http`/`https` apontavam para um app que não existe mais | Configurações → Apps padrão → Zen → Definir padrão |

### Pendente

- 3b: conferir os `rank.plan` por alguns dias (replaneja quando o Magikarp pontuar, ao subir de nível, por tempo
  no alvo e quando a janela de 50 abates encher). O abates/h das hunts nunca visitadas é uma estimativa
  otimista (o padrão da conta); só vai ser medido quando o passo 5 trocar de hunt de verdade.
- 3b, passo 5: escrever a spec (trava de combate e `switch_free_at` antes do `hunt.select`, foco `rank` no
  `restock`, `fallback`, `weekly_ball_budget`).
- Ainda a ver no jogo: o erro de `hunt.select` durante a trava, `m`/`ini` do `estado.topCatch` e se o `welcome`
  traz o `topCatch` da semana.

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
