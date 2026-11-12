-- Stubs mínimos do Supabase para testar as migrations num Postgres comum.
-- Uso: ver supabase/tests/README.md. Nunca rode isto no projeto Supabase.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;

create schema auth;
create table auth.users (id uuid primary key default gen_random_uuid());
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;

create schema vault;
create table vault.secrets (id uuid primary key default gen_random_uuid(), secret text, name text, description text);
create view vault.decrypted_secrets as select id, secret as decrypted_secret, name from vault.secrets;
create function vault.create_secret(s text, n text, d text) returns uuid language sql as
  $$ insert into vault.secrets (secret, name, description) values (s, n, d) returning id $$;
create function vault.update_secret(i uuid, s text) returns void language sql as
  $$ update vault.secrets set secret = s where id = i $$;

grant usage on schema public, auth to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
