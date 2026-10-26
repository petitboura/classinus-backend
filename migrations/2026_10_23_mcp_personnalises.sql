-- Classinus: serveurs MCP personnels. Les jetons sont réservés au backend.
-- Pas de politiques client : les trois tables sont accessibles par service_role uniquement.

create table if not exists public.mcp_personnalises (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    nom text not null check (length(trim(nom)) between 1 and 80),
    url text not null,
    auth_type text not null check (auth_type in ('none', 'bearer', 'oauth')),
    bearer_token text,
    actif boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, url),
    check ((auth_type = 'bearer' and bearer_token is not null) or auth_type <> 'bearer')
);

create index if not exists mcp_personnalises_user_id_created_idx
    on public.mcp_personnalises (user_id, created_at);

create table if not exists public.mcp_personnalises_oauth_temp (
    state text primary key,
    server_id uuid not null references public.mcp_personnalises(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    server_url text not null,
    code_verifier text not null,
    client_id text not null,
    client_secret text,
    token_endpoint text not null,
    issuer text,
    resource_url text not null,
    redirect_uri text not null,
    token_auth_method text not null default 'none',
    created_at timestamptz not null default now()
);

create index if not exists mcp_personnalises_oauth_temp_created_idx
    on public.mcp_personnalises_oauth_temp (created_at);

create table if not exists public.mcp_personnalises_oauth_connections (
    server_id uuid primary key references public.mcp_personnalises(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    client_id text not null,
    client_secret text,
    token_endpoint text not null,
    token_auth_method text not null default 'none',
    resource_url text not null,
    access_token text not null,
    refresh_token text,
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.mcp_personnalises enable row level security;
alter table public.mcp_personnalises_oauth_temp enable row level security;
alter table public.mcp_personnalises_oauth_connections enable row level security;

-- Ne jamais exposer ces tables à anon/authenticated ou à PUBLIC.
revoke all privileges on table
    public.mcp_personnalises,
    public.mcp_personnalises_oauth_temp,
    public.mcp_personnalises_oauth_connections
from public, anon, authenticated;

-- Le backend utilise la clé secrète Supabase (service_role) pour ses routes API.
grant usage on schema public to service_role;
grant all privileges on table
    public.mcp_personnalises,
    public.mcp_personnalises_oauth_temp,
    public.mcp_personnalises_oauth_connections
to service_role;
