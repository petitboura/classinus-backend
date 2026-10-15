-- 15/10/2026, demande Bourama (bouton du modèle en haut du chat, branche
-- frontend feature/bouton-modele-haut) : le dernier modèle choisi par l'élève
-- est gardé sur son compte, pour le retrouver sur n'importe quel appareil
-- (voir api/profiles.py::MonStatutReponse et MettreAJourProfilPayload).
--
-- modele_prefere : identifiant du modèle (ex. deepseek-v4-flash). NULL tant
-- que l'élève n'a jamais choisi : le frontend retombe alors sur DeepSeek Flash.
-- Pas de table à purger : la colonne vit dans profiles, déjà supprimée avec le
-- compte et déjà incluse dans l'export des données (select * sur profiles).

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS modele_prefere text;
