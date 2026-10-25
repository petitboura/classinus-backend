-- Indexer les clés étrangères des tables OAuth MCP personnalisées.
create index if not exists mcp_personnalises_oauth_temp_server_id_idx
    on public.mcp_personnalises_oauth_temp (server_id);
create index if not exists mcp_personnalises_oauth_temp_user_id_idx
    on public.mcp_personnalises_oauth_temp (user_id);
create index if not exists mcp_personnalises_oauth_connections_user_id_idx
    on public.mcp_personnalises_oauth_connections (user_id);
