/*
  Tours de chat detaches persistants (31/10/2026, demande de Bourama : solidite
  Classinus -- travailler en arriere-plan hors de la conversation).

  Avant : core/tours_detaches.py gardait les tours uniquement en memoire du
  processus web. Un redemarrage/deploiement Render perdait le tour en cours et
  tout ce qui n'etait pas encore sauvegarde dans historique_conversations.

  Maintenant : chaque tour connecte est inscrit ici des son demarrage, ses
  lignes SSE sont ecrites par paquets dans tours_chat_evenements_persistes,
  et son statut survit au processus. Au redemarrage, les tours restes
  "en_cours" sans signe de vie sont marques "interrompu" : le texte partiel
  reste rejouable et l'interface propose Continuer, rien n'est perdu.

  Seul le service-role du backend lit/ecrit ces tables. Pas de policy client.
*/
CREATE TABLE IF NOT EXISTS public.tours_chat_persistes (
    id text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id text,
    statut text NOT NULL DEFAULT 'en_cours' CHECK (statut IN ('en_cours', 'termine', 'interrompu')),
    resume jsonb NOT NULL DEFAULT '{}'::jsonb,
    ids_echange jsonb,
    nb_evenements integer NOT NULL DEFAULT 0 CHECK (nb_evenements >= 0),
    cree_le timestamptz NOT NULL DEFAULT now(),
    maj_le timestamptz NOT NULL DEFAULT now(),
    termine_le timestamptz
);

CREATE TABLE IF NOT EXISTS public.tours_chat_evenements_persistes (
    tour_id text NOT NULL REFERENCES public.tours_chat_persistes(id) ON DELETE CASCADE,
    a_partir_de integer NOT NULL CHECK (a_partir_de >= 0),
    lignes jsonb NOT NULL DEFAULT '[]'::jsonb,
    cree_le timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tour_id, a_partir_de)
);

CREATE INDEX IF NOT EXISTS idx_tours_chat_persistes_conversation
    ON public.tours_chat_persistes(user_id, conversation_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_tours_chat_persistes_statut_maj
    ON public.tours_chat_persistes(statut, maj_le);
CREATE INDEX IF NOT EXISTS idx_tours_chat_evenements_tour
    ON public.tours_chat_evenements_persistes(tour_id, a_partir_de);

ALTER TABLE public.tours_chat_persistes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tours_chat_evenements_persistes ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE public.tours_chat_persistes TO service_role;
GRANT ALL ON TABLE public.tours_chat_evenements_persistes TO service_role;
