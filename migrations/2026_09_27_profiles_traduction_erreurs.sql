-- 27/09/2026, demande Bourama (chantier "traduction erreurs execution",
-- branche feature/traduction-erreurs-execution) : traduction IA des
-- messages d'erreur d'exécution de code (voir core/traduction_erreurs.py,
-- api/traduction_erreurs.py, api/profiles.py::MonStatutReponse /
-- MettreAJourProfilPayload), même convention que profiles.est_professeur
-- (migrations/2026_09_06_profiles_est_majeur.sql) : NULL tant que jamais
-- répondu.
--
-- langue_cible_erreurs : langue choisie une seule fois (au premier clic
-- sur "Traduire"), modifiable ensuite dans Paramètres > Préférences.
-- traduction_auto_erreurs : NULL/false = traduction seulement à la
-- demande (bouton "Traduire"), true = traduction automatique dès
-- qu'une erreur apparaît.

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS langue_cible_erreurs text,
    ADD COLUMN IF NOT EXISTS traduction_auto_erreurs boolean;
