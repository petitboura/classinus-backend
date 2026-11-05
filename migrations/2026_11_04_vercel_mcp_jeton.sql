/*
 * ORDRE OBLIGATOIRE : appliquer cette migration AVANT de déployer le code qui
 * l'utilise. Sans elle, le jeton personnel Vercel ne peut pas être enregistré.
 *
 * Vercel passe désormais par un jeton personnel (comme Render), conservé
 * uniquement côté serveur (RLS sans policies), séparément pour chaque compte.
 */
create table if not exists public.vercel_mcp_tokens (
  user_id uuid primary key references auth.users(id) on delete cascade,
  access_token text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.vercel_mcp_tokens enable row level security;
