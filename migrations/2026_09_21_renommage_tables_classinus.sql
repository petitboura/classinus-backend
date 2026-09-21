/*
Renommage des tables au nom de Classinus (21/09/2026).
A executer UNE SEULE FOIS dans Supabase (SQL Editor), puis pousser le code
correspondant. Les donnees et les regles d'acces sont conservees.
IF EXISTS : aucune erreur si une table n'existe pas.
*/

ALTER TABLE IF EXISTS public.clovis_infos RENAME TO classinus_infos;
ALTER INDEX IF EXISTS public.clovis_infos_pkey RENAME TO classinus_infos_pkey;

ALTER TABLE IF EXISTS public.invitations_clovis RENAME TO invitations_classinus;
