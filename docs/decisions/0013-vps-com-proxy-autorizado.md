# 0013 — Worker em VPS com a saída do jogo por proxy ou VPN

- **Status:** Aceita
- **Data:** 2026-11-16
- **Revisa:** [0011](0011-worker-em-ip-residencial.md) (a parte "não usamos proxy, VPN nem outro truque")

## Contexto

- O jogo recusa IP de datacenter com `auth.provedorBanido` (ADR 0011, droplet da DigitalOcean em 12/11).
- Não há máquina que possa ficar ligada 24/7 em casa.
- Em 16/11, o suporte do pokeidle, consultado pelo Discord, disse que **não libera IP** de servidor, mas que
  **pode usar proxy ou VPN**. O bloqueio por provedor existe para barrar bots abusivos, não para impedir a
  automação permitida pelos Termos (seção 5). O print da conversa (quem respondeu, cargo, data) fica guardado
  pelo dono das contas, fora do repositório.
- O pedido formal por e-mail (12/11) segue sem resposta; quando vier, é anexado aqui.

## Decisão

- O worker pode rodar num **VPS**, com o **tráfego do jogo** (WebSocket e os downloads da Pokedex e dos itens)
  saindo por um **proxy ou VPN** configurado em `GAME_PROXY_URL`. O Supabase continua direto, sem proxy.
- **Um IP de saída só, sempre o mesmo**: proxy residencial ou ISP **estático** (dedicado), ou VPN com IP fixo.
  Nada de pool rotativo: trocar de IP a cada conexão muda a "rede" das contas, deixa a contagem de contas por rede
  imprevisível e parece tentativa de driblar o limite.
- Nesse IP só as contas deste projeto: as 3 de farm (a pessoal pode jogar de casa, que é outra rede). Continua
  valendo o limite de 4 contas por pessoa e por rede.
- **Antes de conectar**, o worker confere o IP de saída no ipapi.is (o serviço que a moderação usa, Termos seção 8)
  pelo mesmo caminho do tráfego do jogo. IP de datacenter/hosting **não conecta** (evita somar recusas
  `provedorBanido` na conta). VPN ou proxy marcado não bloqueia, porque foi liberado.
- A credencial do proxy é segredo: só no `.env` do VPS, nunca no log, no banco, no painel ou no repositório.
- Só um worker por conta: o lease já impede dois, mas o worker de casa fica parado enquanto o do VPS roda.

## Consequências

- Worker 24/7 sem depender da casa. Custo: o VPS mais o proxy/VPN de IP fixo (entram no `/compensa` como custo
  da máquina, no lugar da energia).
- A autorização é informal (Discord). Se a moderação ou os Termos mudarem de posição, o worker volta para IP
  residencial e esta ADR é revista. Reler os Termos a cada revisão deles.
- Se o provedor do proxy entregar um IP marcado como datacenter, o worker não sobe e avisa no log: trocar de plano
  ou de provedor, não forçar.

## Alternativas consideradas

- **Liberação do IP do VPS pelo suporte**: preferida, mas negada em 16/11.
- **Pool de proxies residenciais rotativos**: rejeitada (IP muda o tempo todo; ver acima).
- **Máquina dedicada em casa ou celular**: inviável (nada pode ficar ligado em casa; celular é frágil).
