# Diário do projeto

Registro curto do que foi feito em cada dia, o que deu errado e o que ficou pendente.
As decisões em si ficam nos [ADRs](decisions/); aqui fica o caminho até elas.

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
- Fase 3a: confirmar os ids 203, 204 e 206; considerar bolas por abate na regra da bola (medido ~1,2).
- Fase 3b (rank semanal de espécies): desenhar.
- Ver uma captura real (para o `pokemon.captured`): a bola automática "sem parar" (exige VIP) já está
  ligada, mas as 100 Poké Balls acabaram sem captura (chance de 0,3% em Magikarp). Resolvido: com Ultra Balls veio a primeira captura, e o `capturado` virou
  `pokemon.captured` real.
- Fase 4b: implementar os comandos seguindo o desenho.
- Depois: fase 3 (`auto.set`), telemetria de captura vinda do `pkMud` (`pokemon.captured` ainda é
  provisório), retenção dos eventos brutos, métricas do Mercado.
