-- Connexions OAuth individuelles aux serveurs MCP officiels Vercel, Railway et Supabase.
-- Les tables sont accessibles uniquement au backend via la clé service-role.
create table if not exists public.platform_mcp_oauth_temp (
    state text primary key,
    service text not null check (service in ('vercel_mcp', 'railway_mcp', 'supabase_mcp')),
    user_id uuid not null,
    agent_id text,
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

create index if not exists platform_mcp_oauth_temp_created_at_idx
    on public.platform_mcp_oauth_temp (created_at);

create table if not exists public.platform_mcp_oauth_connections (
    user_id uuid not null,
    service text not null check (service in ('vercel_mcp', 'railway_mcp', 'supabase_mcp')),
    client_id text not null,
    client_secret text,
    token_endpoint text not null,
    token_auth_method text not null default 'none',
    resource_url text not null,
    access_token text not null,
    refresh_token text,
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (user_id, service)
);

alter table public.platform_mcp_oauth_temp enable row level security;
alter table public.platform_mcp_oauth_connections enable row level security;

-- No client-side policies: only the trusted backend service-role client may access these tokens.
insert into public.registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
    ('serveur_vercel_mcp', 3, 'vercel_mcp', true, now()),
    ('serveur_railway_mcp', 3, 'railway_mcp', true, now()),
    ('serveur_supabase_mcp', 3, 'supabase_mcp', true, now())
on conflict (nom_outil) do update
set categorie = excluded.categorie,
    nom_serveur = excluded.nom_serveur,
    disponible = excluded.disponible,
    updated_at = now();
