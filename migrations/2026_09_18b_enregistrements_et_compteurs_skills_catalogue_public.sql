-- Chantier profil contributeur / analytique bibliothèque publique (demande
-- Bourama, 18/09/2026, étapes 3/6/7 -- complément).
--
-- 1) enregistrements_count sur bibliotheque_publique et
--    dossiers_catalogue_public : compteur dénormalisé du nombre de fois
--    qu'un élément public a été enregistré dans une bibliothèque perso.
--    - fichier : incrémenté à chaque copie (api/bibliotheque_utilisateur.py
--      ::copier_depuis_bibliotheque_publique), jamais décrémenté (une copie
--      déjà faite reste faite, même si l'utilisateur la supprime ensuite
--      de son côté -- même logique que partages_count/cta_count).
--    - dossier : incrémenté/décrémenté à l'attache/détache
--      (core/dossiers_publics_attaches.py), pour refléter un attachement
--      qui EST réversible (contrairement à la copie de fichier).
--
-- 2) cta_count et partages_count sur comportements_publics (skills) :
--    ces deux compteurs n'existaient jusqu'ici que sur bibliotheque_publique
--    et dossiers_catalogue_public (migration compteurs_partages_cta_
--    catalogue_public du 18/09) -- ajoutés ici pour les skills, même
--    principe que etoiles_count qui, lui, couvre déjà les 3 types
--    (migration etoiles_catalogue_public du 17/09). Pas d'enregistrements_
--    count pour les skills : comportements_publics.activations_count
--    (comportement_public_activations) couvre déjà ce rôle.

ALTER TABLE public.bibliotheque_publique
    ADD COLUMN IF NOT EXISTS enregistrements_count integer NOT NULL DEFAULT 0;

ALTER TABLE public.dossiers_catalogue_public
    ADD COLUMN IF NOT EXISTS enregistrements_count integer NOT NULL DEFAULT 0;

ALTER TABLE public.comportements_publics
    ADD COLUMN IF NOT EXISTS cta_count integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS partages_count integer NOT NULL DEFAULT 0;
