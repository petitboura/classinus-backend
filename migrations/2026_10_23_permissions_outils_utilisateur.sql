-- Permissions MCP personnelles, isolées par utilisateur.
-- Le backend utilise la clé secrète serveur; le frontend n'accède jamais directement à cette table.
create table if not exists public.permissions_outils_utilisateur (
  user_id uuid not null references auth.users(id) on delete cascade,
  nom_outil text not null check (length(trim(nom_outil)) between 1 and 200),
  mode text not null default 'demander'
    check (mode in ('autoriser', 'demander', 'refuser')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, nom_outil)
);

alter table public.permissions_outils_utilisateur enable row level security;

drop policy if exists "Utilisateur propriétaire de ses permissions d'outils"
  on public.permissions_outils_utilisateur;

create policy "Utilisateur propriétaire de ses permissions d'outils"
  on public.permissions_outils_utilisateur
  for all
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

revoke all on table public.permissions_outils_utilisateur from anon, authenticated;
grant select, insert, update on table public.permissions_outils_utilisateur to service_role;
