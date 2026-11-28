# Chantier sections masquées, Communauté et Perso (serveur)

[English version](README.md) · **Version française**

Ouvert le 28 novembre 2026 à la demande de Bourama. Branche `feature/sections-communaute-perso`, partie de `main`, dans les deux dépôts. **Aucun code du serveur n'a encore changé : rien n'est désactivé.** La demande complète, les décisions et l'état de l'interface sont dans le même dossier du dépôt `classinus-frontend`.

## À désactiver, sans rien supprimer

Bureau sauf l'éditeur de code (audit hebdomadaire, codes, programme et catalogue des programmes, établissements, signalements au professeur), les codes partout, les dossiers du téléphone, toute la Concentration, les capacités du téléphone, l'accessibilité, les rappels (y compris l'outil de l'IA). Lever aussi le blocage du chat pour les mineurs sans code.

À conserver : minuteurs, vision de l'écran sur Android (`lire_ecran_telephone`, `marquer_ecran_telephone`), signalement de contenu de la bibliothèque publique (`signalements_router`), proactivité.

## Règles

* Un seul interrupteur réversible, prévu dans `core/fonctions_desactivees.py` (à créer ; le commentaire de `lib/sectionsMasquees.ts` côté interface y renvoie déjà).
* Aucune donnée supprimée ; ne rien retirer de `core/purge_compte.py` ni de l'export des données.
* Messages d'erreur en français et en anglais (`core/erreurs.py`).

## Repères relevés (sur `c2d0e4f`)

### Routes (`api/main.py`, inscriptions vers les lignes 960 à 1025)

À couper : `router_etablissements`, `router_mes_codes`, `router_rattachements`, `router_mode_actif`, `signalements_pedagogiques_router`, `audit_hebdomadaire_corrections_router`, `audit_complet_bureau_router`, `programme_notions_router`, `programme_catalogue_public_router`, `dossiers_designes_router`.

### Tâches de fond (`api/main.py`, démarrage vers les lignes 470 à 488)

À arrêter : `_boucle_planificateur_rappels`, les quatre boucles des dossiers désignés, `_boucle_planificateur_audit_corrections`. Les boucles des minuteurs et de la proactivité sont dans le même bloc `if un_canal_push_disponible()` que les rappels : les garder.

### Outils de l'IA

* `core/registre_outils.py` : `REGISTRE_AFFICHAGE_OUTILS`, groupes vers les lignes 1515 à 1600 et vers 1898, descriptions des catégories vers 1800 à 1822.
* `catalogue_public` : `gerer_programme_catalogue_public`.
* `pedagogie` : `gerer_avancement_notions`, `consulter_avancement_notion`, `verifier_consignes_code_actif`, `consulter_signalement`, `consulter_signalements_pertinents`, `enregistrer_note_signalement`, `rattacher_signalement_notion`. `lire_reponses_qcm` et `changer_mode_conversation` sont dans le même groupe mais ne semblent pas liés aux codes : vérifier, probablement à garder.
* `telephone_etudiant` et groupe téléphone : `gerer_dossier_telephone`, `explorer_dossier`, `gerer_action_mobile`, `lire_temps_ecran`, `gerer_session_concentration` (vérifier le rôle de chacun avant de couper).
* Rappels : `planifier_rappel` (`core/outils_memoire_profil.py` ligne 216, `core/notifications_push.py` ligne 634).
* Fichiers : `core/outils_concentration.py`, `outils_verification_code_actif.py`, `outils_avancement_notions.py`, `outils_signalements.py`, `outils_signalements_espace.py`, `serveur_mcp_espace.py` (serveur MCP public), `outils_mobile.py`, `outils_programme_catalogue_public.py`.
* L'interface envoie `natif` à `/api/chat`, ce qui force `gerer_dossier_telephone` et `explorer_dossier`.

### Codes pendant le chat

* `core/main.py` (imports vers les lignes 24 et 37, vers 774, et 894 à 969 qui forcent `verifier_consignes_code_actif`).
* `core/construction_system_prompt.py` (`code_actif` vers la ligne 316), `core/bibliotheque_rag.py` (vers 312 à 369).
* Aussi : `codes_partage.py`, `signalements.py`, `comportements_etudiants.py`, `programme_notions.py`, `dossiers_publics_attaches.py`, `avancement_notions_ia.py` (`resoudre_code_actif_eleve`, ligne 437), `outils_bibliotheque.py`, `mode_actif_conversation.py`, `bibliotheque_fichiers.py`, `audit_complet_bureau.py`.
* Les contenus reçus par code (fichiers d'origine `code_partage`, dossiers et skills reçus) ne doivent plus apparaître ni servir à l'IA.
* `retirer_elements_destinataires_seuls` (`core/comportements_etudiants.py` vers la ligne 928) écarte du propriétaire les éléments « destinataires seulement » liés à un code. **Décision à prendre avec Bourama** ; compter d'abord les cas dans Supabase.

### Mineurs

* `core/restriction_mineur.py::acces_chat_bloque_pour_mineur` (ligne 44), appelé dans `api/chat.py` ligne 760 et `api/import_ia.py` ligne 58.
* Voir aussi le verrouillage du mode pour les mineurs dans `api/mode_actif_conversation.py`.

## Fin du chantier

Lancer les tests du serveur, vérifier que la liste des outils envoyée au modèle et les routes sont bien coupées, documenter l'interrupteur (français et anglais), relecture indépendante.
