# Deploy: Supabase, worker e painel

> ⚠️ **O jogo recusa IP de datacenter** (`auth.provedorBanido`, ver [ADR 0011](decisions/0011-worker-em-ip-residencial.md)). O tráfego do jogo precisa sair por IP residencial: direto de casa (seção [3a](#3a-pc-de-casa-docker-desktop-no-windows)), por proxy de IP fixo (3b) ou pelo celular (3c).

Guia para subir tudo sem precisar abrir o jogo no computador. Dá para fazer só com o navegador (Supabase) e com o celular (para pegar o token).

> Para o primeiro teste: **uma conta de farm só**, nova, em modo `observe_only` (só escuta), por pouco tempo.

## 1. Supabase

1. Crie um projeto em https://supabase.com (plano grátis). Região: **South America (São Paulo)**.
2. **SQL Editor** → cole e rode, **nesta ordem**, cada arquivo de [`supabase/migrations/`](../supabase/migrations/): `20261112000000_init.sql`, depois `20261112010000_metrics.sql` (métricas e objetivos; liga o pg_cron sozinha) e depois `20261113000000_ouro_liquido.sql` (gasto com consumíveis e ouro líquido) `20261113010000_commands.sql` (comandos do painel) `20261114010000_game_catalog.sql` (catálogo de hunts e Pokedex da fase 3b) e por último `20261115000000_rank_hunt_stats.sql` (entradas do plugin `rank`). Cada arquivo roda **uma vez só**: num projeto que já existe, aplique só os que faltam.
   Com a integração do GitHub ligada (seção 6), as migrations novas rodam sozinhas no push para `main`: não cole mais nenhuma à mão.
3. **Authentication → Users → Add user**: crie o seu usuário. Ele é o dono das contas, e é com ele que você vai entrar no painel depois. Copie o **User UID**.
4. No **SQL Editor**, cadastre a conta de farm:
   ```sql
   insert into public.accounts (owner_id, nick, role)
   values ('<User UID>', '<nick da conta de farm>', 'farm');
   ```
5. **Project Settings → API**: copie a **Project URL** e a **service_role key**. Essa chave dá acesso total, inclusive aos tokens: não cole em lugar nenhum além do `.env` do worker.

## 2. Token pelo celular

Sem console no navegador do celular, use um bookmarklet:

1. No Chrome do celular, crie um favorito qualquer e edite-o:
   - **Nome:** `pokeidle-token`
   - **URL** (tudo numa linha):
     ```
     javascript:(()=>{const s=JSON.parse(localStorage.getItem('sessao')||'{}');prompt('copie:',JSON.stringify({nick:s.nick,token:s.token,dispositivo:localStorage.getItem('id-dispositivo')}))})()
     ```
2. **Use os dados móveis**, não o Wi-Fi do trabalho. Abra pokeidle.io/app em uma **aba anônima** e faça login com a conta de farm.
3. Na barra de endereço, digite `pokeidle-token` e toque no favorito. Uma caixa aparece com `nick`, `token` e `dispositivo`: copie.
4. **Feche a aba anônima sem clicar em "Sair"** (ver [protocolo.md](protocolo.md)).

O bookmarklet só mostra os dados para você: não envia nada para lugar nenhum.

## 3a. PC de casa (Docker Desktop no Windows)

Caminho testado em 12/11/2026: conectou, gravou abates reais e o painel passou a mostrar a conta como `ready`.

1. Abra o **Docker Desktop** e espere o engine subir. Sem ele aberto, o `docker compose` falha com `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`.
2. Na raiz do repo, copie `.env.example` para `.env` e preencha `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`. Deixe `ACCOUNT_1_*` vazio: o token vem do Vault. Vale definir `WORKER_HOLDER=pc-casa`, senão o lease usa o hostname do container, que muda a cada `up`.
3. Grave o token no Vault, se ainda não estiver lá (seção 2 e [worker/README.md](../worker/README.md)).
4. Suba e acompanhe:
   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```

**Mexer na conta na mão** (trocar de hunt, ligar a bola automática, comprar): o jogo só aceita uma sessão por conta, e abrir no navegador derruba o worker (`close 4001`, que ele trata como `NEEDS_LOGIN` e não reconecta).
1. `docker compose stop`;
2. faça o que precisar no navegador;
3. feche a aba **sem "Sair"** (o token do worker continua valendo);
4. `docker compose up -d`.

## 3b. Proxy ou VPN de IP fixo (24/7, ADR 0013)

O tráfego do jogo sai por um proxy ou VPN de **IP fixo**
(residencial ou ISP estático, dedicado), liberado pelo suporte em 16/11.

1. **O proxy**: contrate um IP **estático dedicado** (procure por "static residential" ou "ISP proxy"), nunca um
   pool rotativo. Anote host, porta, usuário e senha e o protocolo (HTTP ou SOCKS5).
2. **O worker**: siga os passos 2 e 3 da seção 3a, com `WORKER_HOLDER=worker-1` e, no `.env`:
   ```bash
   GAME_PROXY_URL=http://usuario:senha@host:porta   # ou socks5://...
   ```
3. **Pare o worker de casa** (`docker compose down` no PC) antes de subir o outro.
4. Suba (`docker compose up -d --build`) e confira no log a primeira linha útil:
   - `IP de saída pelo proxy do jogo: 189.10.x.x (Provedor, tipo isp)`: ok, as sessões sobem em seguida.
   - `IP de saída ... é de datacenter ... Não conectei.`: o proxy entrega IP de datacenter. Troque de plano ou de
     provedor; não force (`EXIT_IP_CHECK=false` só para diagnóstico, nunca para conectar mesmo assim).
5. No painel, na página da conta: **Ping** deve voltar `sessão ready em worker-1`.
6. Em `/economia`, em **Custos do mês**, preencha o fixo (proxy) e marque que a máquina fica ligada de
   qualquer jeito (o PC de casa não entra mais na conta).

## 3c. Saída pelo celular com Tailscale (ADR 0015)

O celular vira o *exit node* da máquina do worker: todo o tráfego dela sai pela internet dele. `GAME_PROXY_URL` fica
vazio. O jogo **nunca** pode ver o IP da máquina, por isso a trava do passo 5.

1. **No celular (Android):** instale o Tailscale, entre na conta, toque em **Exit Node → Run as exit node**.
   Em Configurações → Conexões → Mais configurações de conexão → VPN, ligue **VPN sempre ativa** para o
   Tailscale, e tire o app da otimização de bateria. Deixe na tomada.
2. **No painel do Tailscale** (Machines): no celular, **⋯ → Edit route settings → Use as exit node**. No
   celular e na máquina do worker, **⋯ → Disable key expiry**.
3. **Na máquina do worker:** instale (`curl -fsSL https://tailscale.com/install.sh | sh`, `tailscale up`) e **teste o SSH
   pelo IP 100.x do Tailscale antes do próximo passo**: ligar o exit node derruba o SSH pelo IP público.
4. **Exit node e SSH pelo IP público** (troque `SEU_IP_PUBLICO`):
   ```bash
   tailscale set --exit-node=<nome-do-celular> --exit-node-allow-lan-access
   ip rule add from SEU_IP_PUBLICO lookup main priority 100   # respostas do IP público pela eth0
   ```
   Para a regra voltar no boot, um `public-ip-route.service` (oneshot, `After=tailscaled.service`) com o
   mesmo `ip rule add`.
5. **A trava: containers só saem pela `tailscale0`.**
   ```bash
   cat > /usr/local/sbin/killswitch.sh <<'SH'
   #!/bin/sh
   for IPT in iptables ip6tables; do
     $IPT -N DOCKER-USER 2>/dev/null || true
     for IF in docker0 'br-+'; do
       $IPT -C DOCKER-USER -i "$IF" ! -o tailscale0 -j REJECT 2>/dev/null \
         || $IPT -I DOCKER-USER -i "$IF" ! -o tailscale0 -j REJECT
     done
   done
   SH
   chmod +x /usr/local/sbin/killswitch.sh
   ```
   Um `killswitch.service` (oneshot, `Before=docker.service`, `WantedBy=multi-user.target docker.service`)
   roda o script, e um drop-in `docker.service.d/killswitch.conf` com `ExecStartPost=` roda de novo depois do
   Docker. `systemctl daemon-reload && systemctl enable killswitch.service && /usr/local/sbin/killswitch.sh`.
6. **Prove a trava.** A tabela 52 do Tailscale passa na frente da `main`, então o teste precisa de uma regra
   com prioridade maior:
   ```bash
   ip rule add to 1.1.1.1/32 lookup main priority 99
   curl -s -m 5 https://1.1.1.1/cdn-cgi/trace | grep ip=   # host: o IP da própria máquina (rota pela eth0)
   docker run --rm --network pokeidle-farm_default curlimages/curl -s -m 5 https://1.1.1.1/cdn-cgi/trace | grep ip=   # vazio
   ip rule del priority 99
   iptables -L DOCKER-USER -v -n   # pkts > 0 na regra br-+
   ```
   E o caminho certo: `docker run --rm --network pokeidle-farm_default curlimages/curl -s https://ipinfo.io/org`
   mostra a operadora do celular.
7. **Nunca** rode `tailscale set --exit-node=` para "desfazer" com o worker ligado nem rode o worker fora do
   Docker nessa máquina: a trava só vale para containers.

O worker também confere o IP antes de cada conexão (ADR 0015): no log, `IP de saída não confirmado; não
conectei` ou `IP de saída de datacenter; não conectei` quer dizer que ele esperou em vez de arriscar.

## 4. O que conferir

- Nos logs: `estado=READY`. Se aparecer, o handshake do mapeamento está certo.
- No Supabase, **Table Editor → accounts**: `status = ready`.
- **Table Editor → events**: devem aparecer `state.snapshot`, `session.connected` e, com o tempo, `kill`.
- Eventos `unknown` mostram mensagens que ainda não mapeamos. O `raw` delas ajuda a completar o [protocolo.md](protocolo.md).

Se der errado:

| Log | Provável causa |
|---|---|
| `NEEDS_LOGIN (auth.sessaoInvalida)` | token errado ou vencido; extraia de novo |
| `NEEDS_LOGIN (close 4001...)` | a conta está aberta em outro lugar (aba esquecida?). Feche a aba sem "Sair" e `docker compose up -d` |
| `timeout esperando welcome` repetido | o handshake mudou; precisamos revisar o `hello` |
| `REJECTED (auth.ipBanido / provedorBanido)` | o IP de saída foi barrado. Pare e reavalie o ADR 0011 |

Para parar: `docker compose down`. Para atualizar o código: `git pull && docker compose up -d --build`.

## 5. Painel na Vercel

1. Na Vercel: **Add New → Project**, importe `pokeidle-farm` e em **Root Directory** escolha `web`.
2. **Environment Variables**:
   - `NEXT_PUBLIC_SUPABASE_URL`: a Project URL.
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: a **publishable key** (`sb_publishable_...`), em **Project Settings → API Keys**. Nunca a secreta.
3. **Deploy**. Entre com o e-mail e a senha do usuário do passo 1.3.

Detalhes e como rodar no Codespaces: [web/README.md](../web/README.md).

## 6. Migrations automáticas (integração GitHub do Supabase)

Com isso, todo push para `main` que traz um arquivo novo em `supabase/migrations/` aplica esse arquivo no banco.

1. **Registre as migrations que já foram aplicadas à mão.** A integração compara os arquivos com a tabela
   `supabase_migrations.schema_migrations` e roda todo arquivo sem registro. Como as primeiras foram coladas no
   SQL Editor, essa tabela não existe: sem este passo, ela tentaria rodar tudo de novo e falharia em
   `relation "accounts" already exists`. No **SQL Editor**, uma vez só:
   ```sql
   create schema if not exists supabase_migrations;
   create table if not exists supabase_migrations.schema_migrations (
     version text primary key, statements text[], name text
   );
   insert into supabase_migrations.schema_migrations (version, name) values
     ('20261112000000', 'init'),
     ('20261112010000', 'metrics'),
     ('20261113000000', 'ouro_liquido')
   on conflict (version) do nothing;
   -- a de comandos só entra no registro se já tiver sido aplicada à mão
   insert into supabase_migrations.schema_migrations (version, name)
   select '20261113010000', 'commands' where to_regclass('public.commands') is not null
   on conflict (version) do nothing;
   select version, name from supabase_migrations.schema_migrations order by version;
   ```
2. **Project Settings → Integrations → GitHub Integration**: repositório `luizfsjunior/pokeidle-farm`,
   **Working directory** `.` (a pasta `supabase/` fica na raiz), ligue **Deploy to production** com o branch
   de produção `main`. Deixe **Automatic branching** desligado (branches de preview são pagos e não precisamos).
3. Teste com um push qualquer em `main`. O resultado aparece no próprio commit no GitHub (check do Supabase) e
   no Supabase em **Branches**/**Integrations**.

Regras daqui em diante:
- Migration nova é sempre um arquivo novo com timestamp **maior** que o último (`AAAAMMDDHHMMSS_nome.sql`).
  Nunca edite uma migration que já foi aplicada; corrija com outra.
- Não cole migrations no SQL Editor: o registro fica sem a entrada e o próximo deploy tenta rodar de novo.
- Cada migration roda numa transação: se falhar, nada dela fica no banco. Teste antes no Postgres local
  ([supabase/tests/README.md](../supabase/tests/README.md)).
- Arquivo apagado do repo com registro no banco faz o deploy falhar.

