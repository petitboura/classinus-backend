# Skills publics (backend)

[English version](README.md) · **Version française**

Chantier du 24 novembre 2026, demandé par Bourama : publier un skill publiquement, que l'IA puisse chercher parmi les skills publics et proposer d'en ajouter un, et qu'elle sache quand l'auteur le met à jour. L'auteur peut déjà modifier, supprimer et partager un skill, donc le catalogue repose maintenant sur la vraie table `skills` (fichiers dans R2) à la place de l'ancienne table `comportements_publics`.

## Fonctionnement

- **Publier.** Un skill avec `visibilite = 'public'` est dans le catalogue. Une description est obligatoire (c'est elle qui le fait trouver). Retirer le remet en privé ; les copies déjà ajoutées par d'autres leur restent.
- **Ajouter.** L'ajout crée une copie indépendante avec ses propres fichiers R2, suivie dans `skill_activations` (source, copie, version copiée, date de synchronisation).
- **Mettre à jour.** Chaque modification d'un skill public augmente `version_publique`. La copie ne change jamais toute seule. L'IA prévient une fois (bloc du prompt système « MISES À JOUR DE SKILLS PUBLICS DISPONIBLES »), propose la mise à jour, et ne remplace la copie qu'avec l'accord clair de la personne (outil `gerer_comportement_public`, action `mettre_a_jour`). Le compte rendu dit si la personne avait modifié sa copie.
- **Outil de l'IA.** Actions de `gerer_comportement_public` : `chercher`, `consulter`, `activer`, `publier`, `retirer`, `mises_a_jour`, `mettre_a_jour`. Publier, retirer et mettre à jour demandent une confirmation de la plateforme (`OUTILS_SENSIBLES`).
- **Routes.** `/api/skills-publics` (recherche, détail, publier, retirer, ajouter, liste des mises à jour, mise à jour de la copie). Les anciens identifiants du catalogue fonctionnent encore grâce à `legacy_public_id`.

## Plan du code

- `core/skills_publics.py` : toute la logique, partagée par la page et l'IA.
- `api/skills_publics.py` : routes. `api/skills.py` : hausse de version à la modification.
- `migrations/2026_11_24_skills_publics.sql` : nouvelles colonnes et `skill_activations`.
- `scripts/migrer_skills_vers_r2.py` : déplace les anciennes lignes et relie les anciennes activations (simulation par défaut, `--executer` pour écrire).
- Tests : `test_skills_publics.py`, `test_migration_skills.py`.

## Suppression du compte et export

`skill_activations` est purgée avec le compte (`core/purge_compte.py`) et exportée (`skills_publics_ajoutes` dans `api/profiles.py`). Les clés étrangères suppriment en cascade avec `auth.users`.

## État

Appliqué sur STAGING. La production demande encore, dans cet ordre : la migration SQL, le script de migration (simulation, puis `--executer`, accès R2 nécessaire), puis le backend, puis le frontend. L'ancienne table et l'ancienne route restent jusqu'à validation de Bourama.
