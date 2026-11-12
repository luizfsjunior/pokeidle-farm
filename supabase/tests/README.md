# Testar as migrations localmente

Num Postgres 16 descartável (nunca no projeto Supabase):

```bash
initdb -D /tmp/pg -U postgres && pg_ctl -D /tmp/pg -o "-k /tmp" -l /tmp/pg.log start
createdb -h /tmp -U postgres t
psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f supabase/tests/stubs.sql
for f in supabase/migrations/*.sql; do psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f "$f"; done
psql -h /tmp -U postgres -d t -v ON_ERROR_STOP=1 -f supabase/tests/metrics_test.sql
```

`stubs.sql` imita só o que as migrations usam do Supabase: os papéis `anon`, `authenticated` e `service_role`, `auth.users`, `auth.uid()` e o Vault. O pg_cron é pulado se não estiver instalado.
