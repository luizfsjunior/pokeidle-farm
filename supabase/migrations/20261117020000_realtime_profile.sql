-- O painel assina as mudanças do perfil e das estratégias (Realtime) para a tela acompanhar o jogo
-- em segundos, sem esperar a próxima busca (docs/design/tela-na-hora.md). `commands` já está.
-- O RLS de cada tabela vale também para o Realtime: cada usuário só recebe as próprias contas.

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'account_profile') then
      alter publication supabase_realtime add table public.account_profile;
    end if;
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'strategy_configs') then
      alter publication supabase_realtime add table public.strategy_configs;
    end if;
  end if;
end;
$$;
