-- ORDRE OBLIGATOIRE : appliquer cette migration AVANT de déployer le code qui
-- l'utilise. Sans elle, la clé personnelle Render ne peut pas être enregistrée.
--
-- Render n'accepte pas l'enregistrement OAuth automatique pour Classinus : la
-- connexion passe par la clé personnelle Render, conservée uniquement côté
-- serveur (RLS sans policies), séparément pour chaque compte.
create table if not exists public.render_mcp_tokens (
  user_id uuid primary key references auth.users(id) on delete cascade,
  access_token text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.render_mcp_tokens enable row level security;
