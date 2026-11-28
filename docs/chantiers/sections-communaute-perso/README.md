# Hidden sections, Community and Perso workstream (server)

**English version** · [Version française](README.fr.md)

Opened on 28 November 2026 at Bourama's request. Branch `feature/sections-communaute-perso`, created from `main`, in both repositories. **No server code has changed yet: nothing is disabled.** The full request, decisions and interface status are in the same folder of the `classinus-frontend` repository.

## To disable, without deleting anything

The Bureau except the code editor (weekly audit, codes, curriculum and curriculum catalogue, schools, teacher reports), codes everywhere, phone folders, all of Concentration, phone capabilities, accessibility, reminders (including the AI tool). Also lift the chat block for minors without a code.

Keep: timers, Android screen vision (`lire_ecran_telephone`, `marquer_ecran_telephone`), public library content reporting (`signalements_router`), proactivity.

## Rules

* A single reversible switch, planned as `core/fonctions_desactivees.py` (to be created; the comment in the interface file `lib/sectionsMasquees.ts` already points to it).
* No data deleted; remove nothing from `core/purge_compte.py` or from the data export.
* Error messages in French and English (`core/erreurs.py`).

## Pointers collected (on `c2d0e4f`)

### Routes (`api/main.py`, registrations around lines 960 to 1025)

To cut: `router_etablissements`, `router_mes_codes`, `router_rattachements`, `router_mode_actif`, `signalements_pedagogiques_router`, `audit_hebdomadaire_corrections_router`, `audit_complet_bureau_router`, `programme_notions_router`, `programme_catalogue_public_router`, `dossiers_designes_router`.

### Background tasks (`api/main.py`, startup around lines 470 to 488)

To stop: `_boucle_planificateur_rappels`, the four designated folder loops, `_boucle_planificateur_audit_corrections`. The timer and proactivity loops sit in the same `if un_canal_push_disponible()` block as reminders: keep them.

### AI tools

* `core/registre_outils.py`: `REGISTRE_AFFICHAGE_OUTILS`, groups around lines 1515 to 1600 and around 1898, category descriptions around 1800 to 1822.
* `catalogue_public`: `gerer_programme_catalogue_public`.
* `pedagogie`: `gerer_avancement_notions`, `consulter_avancement_notion`, `verifier_consignes_code_actif`, `consulter_signalement`, `consulter_signalements_pertinents`, `enregistrer_note_signalement`, `rattacher_signalement_notion`. `lire_reponses_qcm` and `changer_mode_conversation` are in the same group but do not appear tied to codes: check, probably keep.
* `telephone_etudiant` and the phone group: `gerer_dossier_telephone`, `explorer_dossier`, `gerer_action_mobile`, `lire_temps_ecran`, `gerer_session_concentration` (check what each does before cutting).
* Reminders: `planifier_rappel` (`core/outils_memoire_profil.py` line 216, `core/notifications_push.py` line 634).
* Files: `core/outils_concentration.py`, `outils_verification_code_actif.py`, `outils_avancement_notions.py`, `outils_signalements.py`, `outils_signalements_espace.py`, `serveur_mcp_espace.py` (public MCP server), `outils_mobile.py`, `outils_programme_catalogue_public.py`.
* The interface sends `natif` to `/api/chat`, which forces `gerer_dossier_telephone` and `explorer_dossier`.

### Codes during chat

* `core/main.py` (imports around lines 24 and 37, around 774, and 894 to 969 which force `verifier_consignes_code_actif`).
* `core/construction_system_prompt.py` (`code_actif` around line 316), `core/bibliotheque_rag.py` (around 312 to 369).
* Also: `codes_partage.py`, `signalements.py`, `comportements_etudiants.py`, `programme_notions.py`, `dossiers_publics_attaches.py`, `avancement_notions_ia.py` (`resoudre_code_actif_eleve`, line 437), `outils_bibliotheque.py`, `mode_actif_conversation.py`, `bibliotheque_fichiers.py`, `audit_complet_bureau.py`.
* Content received through a code (files with origin `code_partage`, received folders and skills) must no longer appear or be used by the AI.
* `retirer_elements_destinataires_seuls` (`core/comportements_etudiants.py` around line 928) withholds "recipients only" elements linked to a code from their owner. **To be decided with Bourama**; count the cases in Supabase first.

### Minors

* `core/restriction_mineur.py::acces_chat_bloque_pour_mineur` (line 44), called in `api/chat.py` line 760 and `api/import_ia.py` line 58.
* See also the mode locking for minors in `api/mode_actif_conversation.py`.

## Finishing

Run the server tests, check that the tool list sent to the model and the routes are really cut, document the switch (French and English), independent review.
