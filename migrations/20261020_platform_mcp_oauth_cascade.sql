/*
  Classinus : les tables platform_mcp_oauth_* doivent suivre la suppression du
  compte (ON DELETE CASCADE vers auth.users), comme les tables Higgsfield.
  A appliquer APRES 20261020_platform_mcp_oauth.sql. Sans danger si la
  contrainte existe deja. Les lignes orphelines eventuelles sont retirees
  d'abord, sinon la contrainte ne pourrait pas etre posee.
*/
delete from public.platform_mcp_oauth_temp
  where user_id not in (select id from auth.users);
delete from public.platform_mcp_oauth_connections
  where user_id not in (select id from auth.users);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'platform_mcp_oauth_temp_user_fk') then
    alter table public.platform_mcp_oauth_temp
      add constraint platform_mcp_oauth_temp_user_fk
      foreign key (user_id) references auth.users(id) on delete cascade;
  end if;
  if not exists (select 1 from pg_constraint where conname = 'platform_mcp_oauth_connections_user_fk') then
    alter table public.platform_mcp_oauth_connections
      add constraint platform_mcp_oauth_connections_user_fk
      foreign key (user_id) references auth.users(id) on delete cascade;
  end if;
end $$;

create index if not exists platform_mcp_oauth_temp_user_id_idx
  on public.platform_mcp_oauth_temp (user_id);
