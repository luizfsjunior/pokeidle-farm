# 0015 — Saída do jogo pelo celular (Tailscale) e trava contra o IP do droplet

- **Status:** Aceita
- **Data:** 2026-11-24
- **Revisa:** [0013](0013-servidor-com-proxy-autorizado.md) (a parte "um IP de saída só, sempre o mesmo" e a
  conferência do IP só na subida)

## Contexto

- Em 23/11 a saída do jogo passou do proxy ISP da IPRoyal para um "Residencial Fixo" da GTI Proxy. No mesmo
  dia, a `luizfsjunior_3` foi recusada com `login.limiteOnlineIp` ("Esta rede já está com 4 contas
  conectadas") saindo pelo IP da GTI, com só duas contas nossas ligadas: o IP vendido como dedicado tinha
  gente de fora.
- O celular (Android, Tailscale) passou a ser o *exit node* do droplet: todo o tráfego do droplet sai pela
  internet do celular (Wi-Fi de casa ou 4G da operadora). As quatro contas conectaram com o IP da
  Telefônica, no mesmo ritmo de abates de antes.
- O jogo **nunca** pode ver o IP da DigitalOcean (ADR 0011). Com o exit node, há caminhos em que o droplet
  volta a sair pela `eth0`: `tailscale set --exit-node=` (ou `down`/`logout`), o `tailscaled` parado, a
  chave do aparelho expirada.
- A conferência do IP na subida era permissiva ("não consegui conferir o IP de saída ... sigo assim
  mesmo"), e a de cada reconexão corria em paralelo com a conexão e só ia para o evento.

## Decisão

- **Saída pelo celular**, como exit node do Tailscale. `GAME_PROXY_URL` fica vazio: o container sai pela
  rota padrão, que é a `tailscale0`.
- **Trava de rede no droplet** (`/usr/local/sbin/killswitch.sh`, ver deploy.md, seção 3c): na chain
  `DOCKER-USER`, qualquer pacote dos containers que tente sair por outra interface que não a `tailscale0` é
  recusado. Sobe antes do Docker (`killswitch.service`) e de novo no `ExecStartPost` dele. Se o Tailscale
  cair, o worker fica sem rede (nem o Supabase), nunca com a da DigitalOcean.
- **Trava no worker** (segunda camada, vale fora desse droplet também):
  - antes de **cada** conexão, a sessão confere o IP de saída e espera a resposta. Datacenter ou sem
    confirmação: não abre o WebSocket, registra `session.disconnected` e tenta de novo pelo backoff;
  - na subida, sem confirmação, o worker espera e confere de novo em vez de seguir;
  - os downloads do jogo (Pokedex, itens, arquivos) passam pelo `ExitGuard`, com a confirmação valendo
    10 min;
  - se o ipapi.is falhar, pergunta ao ip-api.com (o campo `hosting` marca datacenter). Os dois fora: sem
    confirmação, não conecta.
- O IP de saída pode mudar (4G, troca de antena). Continua valendo o que importa na ADR 0013: não é pool
  rotativo de proxy, é a conexão de uma pessoa, e no Wi-Fi de casa fica estável.

## Consequências

- Sem custo de proxy. Custo em dados móveis quando o celular está no 4G: o celular conta as duas pernas
  (recebe do jogo e reenvia ao droplet), cerca de 85 MB/h com as 4 contas, medido em 23/11.
- O worker para quando o celular fica sem rede ou sem bateria; volta sozinho (backoff de até 5 min).
- No 4G, cada troca de IP derruba e reconecta as sessões.
- O host do droplet ainda consegue sair pela `eth0` (a trava é só para containers): o worker roda sempre
  no Docker.
- O nó de saída no Android é mais lento que no Linux. Com as 4 contas não fez diferença no ritmo.

## Alternativas consideradas

- **Continuar na GTI Proxy**: rejeitada (IP compartilhado, R$ 40/mês).
- **Só a trava de rede**: aceita como principal, mas a do worker fica porque vale em qualquer máquina.
- **Confiar só na conferência do worker**: insuficiente, há uma janela entre a consulta e a conexão.
