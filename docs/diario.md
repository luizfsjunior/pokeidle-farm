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
| Card mostra "Rejeitada" | status que ficou da tentativa no droplet; o simulador não mexe em status | normal; o worker atualiza quando rodar em casa |

### Pendente

- Apagar o droplet da DigitalOcean e os *Actions secrets* que sobraram.
- Testar o worker em casa (IP residencial) e confirmar o protocolo no DevTools.
- Esperar a resposta do suporte sobre VPS/proxy (ADR 0011).
- Fase 4b: implementar os comandos seguindo o desenho.
- Depois: fase 3 (`auto.set`), telemetria de captura vinda do `pkMud` (`pokemon.captured` ainda é
  provisório), retenção dos eventos brutos, métricas do Mercado.
