/*
  Versions navigables, deuxieme lot (26/10/2026, demande de Bourama).

  1. selectionne_le : date a laquelle une version a ete choisie par
     l'utilisateur (fleches de version du chat). A chaque embranchement,
     le rechargement affiche la version dont coalesce(selectionne_le,
     created_at) est la plus recente. Une version neuve (created_at tout
     frais) passe donc devant, et un retour vers une ancienne version via
     les fleches la fait repasser devant. Colonne ajoutee a une table deja
     purgee et exportee avec le compte (core/purge_compte.py, export
     select("*")) : rien d'autre a ajouter pour la suppression du compte.

  2. Rattachement des anciennes lignes. Les echanges enregistres avant
     la migration 2026_09_20c (appliquee en production le 21/09/2026 a
     23:01:15 UTC) ont tous parent_id NULL : le chat les lit comme autant
     de racines freres, donc comme autant de versions alternatives au
     premier message. On les rechaine ici dans l'ordre (created_at puis id,
     la question puis sa reponse ont le meme created_at quand elles ont ete
     inserees ensemble) pour chaque fil. Ne touche que les lignes creees
     avant cette date, qui n'ont jamais eu de vraie branche. Rejouable sans
     effet : une ligne qui a deja un parent n'est pas modifiee.
*/

ALTER TABLE public.historique_conversations
    ADD COLUMN IF NOT EXISTS selectionne_le timestamptz;

WITH ordonnees AS (
    SELECT
        id,
        lag(id) OVER (
            PARTITION BY user_id, agent_id, conversation_id
            ORDER BY created_at, id
        ) AS precedent_id
    FROM public.historique_conversations
)
UPDATE public.historique_conversations AS h
SET parent_id = o.precedent_id
FROM ordonnees AS o
WHERE h.id = o.id
  AND h.parent_id IS NULL
  AND o.precedent_id IS NOT NULL
  AND h.created_at < timestamptz '2026-09-21 23:01:15+00';
