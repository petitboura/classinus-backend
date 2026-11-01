/*
  Rechainage des conversations anciennes, troisieme lot (31/10/2026,
  demande de Bourama : "regarde encore s'il y a pas autre probleme de
  restructuration", suite a la migration du 26/10/2026).

  Audit du meme jour sur la production (5 091 lignes, 709 fils) :
  - 83 fils avaient encore plusieurs racines. Echantillon controle :
    ce sont des questions qui se suivent, pas des versions du premier
    message (aucune de ces racines n'a de selectionne_le, donc aucune
    n'a ete choisie un jour via les fleches de version). A la
    reouverture, le frontend ne montre qu'une branche : les autres
    echanges sont invisibles alors qu'ils sont en base.
  - 3 questions etaient rattachees a une autre question au lieu de la
    reponse precedente : elles devenaient les soeurs de cette reponse,
    donc affichees comme des versions alternatives d'elle.
  - Le groupe "legacy" (conversation_id NULL, un seul utilisateur et
    un seul agent concernes, 20 lignes) avait 10 racines pour le meme
    probleme.

  Correctif, dans l'ordre chronologique stable (created_at puis id) de
  chaque groupe (user_id, agent_id, conversation_id, NULL compris) :
  1. une question dont le parent est une question est rattachee a la
     ligne qui la precede immediatement dans son groupe ;
  2. toute racine sauf la premiere de son groupe est rattachee a la
     ligne qui la precede immediatement dans son groupe.
  Rejouable sans effet : apres passage, il ne reste qu'une racine par
  groupe et plus aucune question fille d'une question.
*/

WITH ordonnees AS (
    SELECT
        id,
        role,
        parent_id,
        lag(id) OVER (
            PARTITION BY user_id, agent_id, conversation_id
            ORDER BY created_at, id
        ) AS precedent_id
    FROM public.historique_conversations
)
UPDATE public.historique_conversations AS h
SET parent_id = o.precedent_id
FROM ordonnees AS o
JOIN public.historique_conversations AS parent_actuel ON parent_actuel.id = o.parent_id
WHERE h.id = o.id
  AND h.role = 'user'
  AND parent_actuel.role = 'user'
  AND o.precedent_id IS NOT NULL
  AND o.precedent_id <> h.parent_id;

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
  AND o.precedent_id IS NOT NULL;
