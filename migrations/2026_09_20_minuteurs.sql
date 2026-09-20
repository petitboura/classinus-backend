-- 20/09/2026, demande Bourama : minuteurs dans le chat (voir
-- core/minuteurs.py, core/outils_minuteurs.py, api/minuteurs.py).
--
-- Un minuteur est enregistre CHEZ NOUS (pas seulement dans la page de
-- l'etudiant) pour qu'il survive a un changement de page, une
-- fermeture de l'appli ou une ouverture sur un autre appareil. La fin
-- prevue est un instant absolu (fin_prevue), jamais un compteur qui
-- descend : arreter ou modifier un minuteur ne fait que changer cette
-- ligne, tous les appareils affichent donc le meme temps restant.
--
-- statut :
--   en_cours : tourne (ou vient de finir sans que personne ne l'ait
--              encore "pris en charge", voir /terminer dans
--              api/minuteurs.py)
--   termine  : la fin a ete prise en charge (une seule fois, meme si
--              l'appli est ouverte a plusieurs endroits)
--   arrete   : arrete par l'etudiant ou par Clovis
--
-- action_fin : ce que Clovis fera a la fin, ecrit au lancement (par
-- Clovis, deduit de la conversation ou demande a l'etudiant). NULL si
-- rien n'est prevu : Clovis decidera alors selon la conversation.
--
-- titre NULL : l'affichage utilise son propre texte par defaut
-- (traduisible), jamais une chaine fixe stockee ici.

CREATE TABLE IF NOT EXISTS public.minuteurs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    conversation_id uuid,
    titre text,
    duree_secondes integer NOT NULL CHECK (duree_secondes > 0),
    fin_prevue timestamptz NOT NULL,
    statut text NOT NULL DEFAULT 'en_cours' CHECK (statut IN ('en_cours', 'termine', 'arrete')),
    action_fin text,
    lance_par text NOT NULL CHECK (lance_par IN ('clovis', 'etudiant')),
    notification_envoyee boolean NOT NULL DEFAULT false,
    cree_le timestamptz NOT NULL DEFAULT now(),
    modifie_le timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_minuteurs_user_statut
    ON public.minuteurs USING btree (user_id, statut);

-- Sert au planificateur de notifications (minuteurs finis dont
-- l'etudiant n'a pas ete prevenu) : ne parcourt que les minuteurs
-- encore en cours.
CREATE INDEX IF NOT EXISTS idx_minuteurs_en_cours_fin
    ON public.minuteurs USING btree (fin_prevue)
    WHERE statut = 'en_cours' AND notification_envoyee = false;

ALTER TABLE public.minuteurs ENABLE ROW LEVEL SECURITY;
-- Aucune policy definie : acces exclusivement via la cle service_role
-- (backend), meme logique que les tables voisines du projet.
