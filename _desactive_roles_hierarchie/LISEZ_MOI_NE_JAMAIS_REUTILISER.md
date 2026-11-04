# Never reuse: disabled area

[English version] · [Français](LISEZ_MOI_NE_JAMAIS_REUTILISER.fr.md)

These files were moved here on 6 September 2026 during Part 9 of the pedagogical-trust project (new school system; see `core/etablissements.py` and `api/etablissements.py`).

## Contents

- `api/roles.py`: old fixed role hierarchy (school / teacher / student), migration `2026_08_04_roles_hierarchie.sql`. No `app.include_router(...)` had connected it in `api/main.py` even before the move, so none of its endpoints was reachable.
- `api/invitations_clovis.py`: a shareable-code variant of the same fixed relationship system. Same finding: it was not connected.

## Why the files were moved instead of deleted

The root issue was that `profiles.role`, `etablissement_id`, and `enseignant_id` are fixed columns selected once and not editable. This is incompatible with the new model of multiple, editable relationships (follow / connect / accept) requested by Bourama for Point 6 of the pedagogical-trust vision document.

Reshaping `roles.py` for the new model would have broken the fixed schema. The decision was therefore to start again with entirely separate tables (`etablissements`, `etablissements_rattachements`, and `etablissements_publications`) instead of reusing or reshaping this code.

The files remain on disk so Bourama can review the old logic if needed, but they must never be reconnected or have their schema copied without asking him explicitly again.

## What was extracted BEFORE the move (important)

`api/roles.py` also contained `resoudre_destinataire_autorise` and `_inserer_message`, which are actively used by the AI `envoyer_message` tool (direct messaging based on the hierarchy, through `core/outils_memoire_profil.py` → `core/serveur_mcp_generation.py`).

These functions and their dependencies (`_contacts_autorises`, `_peut_echanger_messages`, `_profils_par_colonne`, `_etablissement_de_etudiant`, `_nom_affiche_ou_repli`) were extracted unchanged into `core/messagerie_directe.py` before the move. There was no behavior change: `envoyer_message` continues to work as before. `api/roles.py` now imports these functions from `core/messagerie_directe.py` instead of defining them again.

`api/permissions_hierarchie.py`, which is used by `api/agents.py`, remains untouched in its normal location under `api/`. It was not moved and is still active.
