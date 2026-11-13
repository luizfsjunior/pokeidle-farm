# Testar as migrations localmente

No projeto Supabase as migrations rodam sozinhas no push para `main` (integração GitHub, ver
[docs/deploy.md](../../docs/deploy.md), seção 6). Teste aqui antes de enviar: uma migration que falha lá
não é aplicada, mas trava as seguintes até ser corrigida.

Num Postgres 16 descartável (nunca no projeto Supabase):

```bash
initdb -D /tmp/pg -U postgres && pg_ctl -D /tmp/pg -o "-k /tmp" -l /tmp/pg.log start
createdb -h /tmp -U postgres t
psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f supabase/tests/stubs.sql
for f in supabase/migrations/*.sql; do psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f "$f"; done
psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f supabase/tests/metrics_test.sql
psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f supabase/tests/ouro_liquido_test.sql
psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f supabase/tests/commands_test.sql
```

`stubs.sql` imita só o que as migrations usam do Supabase: os papéis `anon`, `authenticated` e `service_role`, `auth.users`, `auth.uid()` e o Vault. O pg_cron é pulado se não estiver instalado.

O `metrics_test.sql` precisa de eventos do simulador no banco. O `ouro_liquido_test.sql` e o `commands_test.sql` criam os próprios
dados (numa hora de 2001) e apaga no fim, então roda num banco vazio.

Sem Postgres instalado (Windows), dá para usar a imagem `postgres:16`. O entrypoint reinicia o servidor
depois do `initdb`, então espere a **segunda** linha "ready to accept connections" antes do `createdb`:

```bash
docker run --rm -v "$PWD/supabase:/s:ro" -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16 sh -c '
docker-entrypoint.sh postgres >/tmp/pg.log 2>&1 &
for i in $(seq 60); do [ "$(grep -c "ready to accept connections" /tmp/pg.log)" -ge 2 ] && break; sleep 1; done
createdb -U postgres t
P="psql -q -U postgres -d t -v ON_ERROR_STOP=1"
$P -f /s/tests/stubs.sql && for f in /s/migrations/*.sql; do $P -f "$f" || exit 1; done && $P -f /s/tests/ouro_liquido_test.sql'
```
