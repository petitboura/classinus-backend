-- ORDRE OBLIGATOIRE : appliquer cette migration AVANT de déployer le code qui
-- l'utilise. Sans elle, Render, Cloudflare et Microsoft ne peuvent pas se
-- connecter et la table des jetons Netlify n'existe pas.
--
-- Connexions MCP supplémentaires utilisées par Classinus (23/10/2026).
-- Google Workspace (hors Drive, déjà présent), Render et Cloudflare passent
-- par leurs endpoints MCP officiels. Microsoft MCP Enterprise est en preview
-- et nécessite une configuration OAuth Entra dédiée. Netlify utilise un
-- jeton personnel stocké uniquement côté backend (RLS sans policies).
alter table public.platform_mcp_oauth_temp
  drop constraint if exists platform_mcp_oauth_temp_service_check;
alter table public.platform_mcp_oauth_connections
  drop constraint if exists platform_mcp_oauth_connections_service_check;

alter table public.platform_mcp_oauth_temp
  add constraint platform_mcp_oauth_temp_service_check
  check (service in ('vercel_mcp', 'railway_mcp', 'supabase_mcp', 'render_mcp', 'cloudflare_mcp', 'microsoft_mcp'));
alter table public.platform_mcp_oauth_connections
  add constraint platform_mcp_oauth_connections_service_check
  check (service in ('vercel_mcp', 'railway_mcp', 'supabase_mcp', 'render_mcp', 'cloudflare_mcp', 'microsoft_mcp'));

create table if not exists public.netlify_mcp_tokens (
  user_id uuid primary key references auth.users(id) on delete cascade,
  access_token text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.netlify_mcp_tokens enable row level security;

insert into public.registre_outils_plateforme (nom_outil, categorie, nom_serveur, disponible, updated_at)
values
  ('serveur_render_mcp', 3, 'render_mcp', true, now()),
  ('serveur_cloudflare_mcp', 3, 'cloudflare_mcp', true, now()),
  ('serveur_microsoft_mcp', 3, 'microsoft_mcp', true, now()),
  ('serveur_netlify_mcp', 3, 'netlify_mcp', true, now()),
  ('serveur_google_gmail_mcp', 3, 'google_gmail_mcp', true, now()),
  ('serveur_google_docs_mcp', 3, 'google_docs_mcp', true, now()),
  ('serveur_google_sheets_mcp', 3, 'google_sheets_mcp', true, now()),
  ('serveur_google_slides_mcp', 3, 'google_slides_mcp', true, now()),
  ('serveur_google_calendar_mcp', 3, 'google_calendar_mcp', true, now()),
  ('serveur_google_chat_mcp', 3, 'google_chat_mcp', true, now()),
  ('serveur_google_classroom_mcp', 3, 'google_classroom_mcp', true, now()),
  ('serveur_google_people_mcp', 3, 'google_people_mcp', true, now())
on conflict (nom_outil) do update
set categorie = excluded.categorie,
    nom_serveur = excluded.nom_serveur,
    disponible = excluded.disponible,
    updated_at = now();
