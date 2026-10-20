-- Classinus: stockage OAuth DCR Higgsfield, tokens isolés par utilisateur.
-- À appliquer dans Supabase avant d'activer le connecteur.
create table if not exists public.higgsfield_oauth_temp (
  state text primary key,
  user_id text not null,
  agent_id text,
  code_verifier text not null,
  client_id text not null,
  client_secret text,
  redirect_uri text not null,
  issuer text not null,
  token_endpoint text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.higgsfield_oauth_connections (
  user_id text primary key,
  client_id text not null,
  client_secret text,
  issuer text not null,
  token_endpoint text not null,
  access_token text not null,
  refresh_token text,
  expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);

create index if not exists higgsfield_oauth_temp_created_at_idx
  on public.higgsfield_oauth_temp (created_at);

alter table public.higgsfield_oauth_temp enable row level security;
alter table public.higgsfield_oauth_connections enable row level security;
