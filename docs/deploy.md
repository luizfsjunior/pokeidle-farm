# Deploy: Supabase, worker e painel

> ⚠️ **O jogo bloqueia conexões da DigitalOcean** (`auth.provedorBanido`, ver [ADR 0011](decisions/0011-worker-em-ip-residencial.md)). O worker precisa rodar numa máquina com **IP residencial**. O caminho testado é a seção [3a (PC de casa com Docker Desktop)](#3a-pc-de-casa-docker-desktop-no-windows). A seção 3 (droplet) fica só como referência de comandos.

Guia para subir tudo sem precisar abrir o jogo no computador. Dá para fazer só com o navegador (Supabase e console web da DigitalOcean) e com o celular (para pegar o token).

> ⚠️ A conexão a partir de IP de datacenter ainda é uma decisão em aberto ([ADR 0004](decisions/0004-hospedagem-digitalocean.md)). Para o primeiro teste: **uma conta de farm só**, nova, em modo `observe_only` (só escuta), por pouco tempo.

## 1. Supabase

1. Crie um projeto em https://supabase.com (plano grátis). Região: **South America (São Paulo)**.
2. **SQL Editor** → cole e rode, **nesta ordem**, cada arquivo de [`supabase/migrations/`](../supabase/migrations/): `20261112000000_init.sql`, depois `20261112010000_metrics.sql` (métricas e objetivos; liga o pg_cron sozinha) e depois `20261113000000_ouro_liquido.sql` (gasto com consumíveis e ouro líquido). Cada arquivo roda **uma vez só**: num projeto que já existe, aplique só os que faltam.
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

## 3. Droplet

1. Na DigitalOcean, crie um droplet: **Ubuntu 24.04**, plano **Basic de US$ 4** (512 MB), região **NYC** ou **ATL**.
2. Abra o **Console** (botão no painel do droplet; funciona pelo navegador, sem SSH).
3. Instale o Docker e baixe o projeto:
   ```bash
   curl -fsSL https://get.docker.com | sh
   git clone https://github.com/luizfsjunior/pokeidle-farm.git
   cd pokeidle-farm
   ```
4. Crie o `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Preencha `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` e `WORKER_HOLDER=droplet-1`. Deixe `ACCOUNT_1_*` vazio.
5. Grave o token no Vault. Ele é pedido sem aparecer na tela:
   ```bash
   docker compose run --rm worker set-token --nick <nick> --device <dispositivo>
   ```
6. Suba o worker:
   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```

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
| `REJECTED (auth.ipBanido / provedorBanido)` | o IP do droplet foi barrado. Pare e reavalie o ADR 0004 |

Para parar: `docker compose down`. Para atualizar o código: `git pull && docker compose up -d --build`.

## 5. Painel na Vercel

1. Na Vercel: **Add New → Project**, importe `pokeidle-farm` e em **Root Directory** escolha `web`.
2. **Environment Variables**:
   - `NEXT_PUBLIC_SUPABASE_URL`: a Project URL.
   - `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`: a **publishable key** (`sb_publishable_...`), em **Project Settings → API Keys**. Nunca a secreta.
3. **Deploy**. Entre com o e-mail e a senha do usuário do passo 1.3.

Detalhes e como rodar no Codespaces: [web/README.md](../web/README.md).

