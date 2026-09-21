-- Chantier "versions navigables" (20/09/2026, demande Bourama) : modifier
-- ou réessayer un message écrasait purement et simplement l'ancienne
-- réponse, sans aucun moyen d'y revenir. Décision Bourama : versionnement
-- complet n'importe où dans la conversation (pas seulement le dernier
-- échange), en une seule fois, avec persistance dès le départ.
--
-- Modèle retenu : chaque ligne de historique_conversations pointe vers la
-- ligne PRÉCÉDENTE dans sa branche via parent_id (NULL pour le tout
-- premier message d'une conversation). Plusieurs lignes peuvent partager
-- le MÊME parent_id : ce sont des versions alternatives à ce point précis
-- (soit plusieurs réponses assistant pour la même question, "réessayer",
-- soit plusieurs messages utilisateur pour la même suite, "modifier").
-- L'API (voir api/historique.py:obtenir_fil_conversation) renvoie
-- désormais TOUTES les lignes (toutes les branches, pas seulement le
-- chemin actif) ; c'est le frontend qui reconstruit l'arbre et choisit
-- quoi afficher par défaut (la version la plus récente à chaque
-- embranchement), voir ChatIA.tsx.
--
-- ON DELETE SET NULL plutôt que CASCADE : si une ligne parente est un
-- jour supprimée (signalement, RGPD...), ses enfants ne doivent pas
-- disparaître avec elle, ils deviennent simplement des racines
-- orphelines plutôt que de perdre des réponses entières silencieusement.

ALTER TABLE public.historique_conversations
    ADD COLUMN IF NOT EXISTS parent_id bigint REFERENCES public.historique_conversations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_historique_conversations_parent
    ON public.historique_conversations USING btree (parent_id);
