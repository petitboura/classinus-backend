/*
  Classinus : compteur quotidien des generations MCP partagees Higgsfield.

  Etend la table higgsfield_usage (migration 2026_10_25_higgsfield_usage.sql)
  au genre "mcp" : les fonctions MCP-only tournent sur le compte partage de
  Classinus, chaque appel est donc compte par utilisateur et par jour, comme
  les videos et les images de l'API. Plafond regle par la variable Railway
  HIGGSFIELD_LIMITE_MCP_PAR_JOUR (defaut 10 dans core/higgsfield_limites.py).

  A appliquer dans Supabase avant de deployer le backend qui utilise le
  genre "mcp", sinon la reservation echoue et la generation est refusee.
*/

alter table public.higgsfield_usage
  drop constraint if exists higgsfield_usage_genre_check;

alter table public.higgsfield_usage
  add constraint higgsfield_usage_genre_check
  check (genre in ('video', 'image', 'mcp'));
