/*
22/10/2026, demande Bourama (traduction de l'interface) : la langue de
l'interface (fr ou en) est choisie à la création du compte puis modifiable
dans Paramètres, et gardée sur le compte pour la retrouver sur n'importe
quel appareil (voir api/profiles.py::MonStatutReponse et
MettreAJourProfilPayload, même principe que profiles.modele_prefere).

langue_interface : 'fr' ou 'en'. NULL tant que jamais choisie : le frontend
garde alors la langue de l'appareil et l'enregistre sur le compte.
La colonne vit dans profiles : supprimée avec le compte, incluse dans l'export.
*/

ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS langue_interface text;
