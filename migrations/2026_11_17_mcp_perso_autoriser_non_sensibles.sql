-- Classinus: serveurs MCP personnels. Réglage par serveur : la personne autorise une fois pour
-- toutes les outils non sensibles (lecture seule) de ce serveur, au lieu de les confirmer un par un.
-- Les outils sensibles continuent de demander une confirmation. Valeur par défaut : false.
-- La ligne appartient déjà à l'utilisateur (cascade vers auth.users), rien à ajouter à la purge du compte.

alter table public.mcp_personnalises
    add column if not exists autoriser_non_sensibles boolean not null default false;
