> [English version](./CLAUDE.md) · **Version française**

# Instructions permanentes pour Claude sur ce dépôt

## Jamais de tirets doubles ("--") dans un texte AFFICHÉ

Bourama déteste totalement les "--" (substitut d'em-dash) dans tout texte
qu'un utilisateur ou lui-même voit à l'écran. Concrètement, jamais dans :
- les messages d'erreur renvoyés par l'API (`erreur_api`, exceptions, etc.)
- le texte que les outils MCP renvoient à l'IA pour être relayé en chat
  (core/serveur_mcp_espace.py, core/serveur_mcp_generation.py)
- tout label, nom, description généré dynamiquement et stocké en base
  pour être affiché (skills, comportements, plugins...)

Ça reste totalement acceptable dans :
- le code lui-même (commentaires, docstrings) -- jamais vu par l'utilisateur
- les séparateurs markdown intentionnels type `"\n\n---\n\n"` (ligne
  horizontale), ce n'est pas un em-dash, c'est un délimiteur de section

À la place d'un em-dash dans un texte affiché : une virgule, un point, une
parenthèse, ou reformuler la phrase. Exemple concret corrigé le 20/08/2026 :
`f"(Source : {nom} -- {url})"` → `f"(Source : {nom}, {url})"`.

Cette règle est un standing instruction : la vérifier avant de livrer tout
texte destiné à être affiché, sans que Bourama ait à la répéter.

## Toute nouvelle donnée liée à un utilisateur doit être purgée à la suppression du compte

Erreur constatée le 12/10/2026 : la suppression de compte
(`api/profiles.py`, fonction `supprimer_mon_compte`) ne supprimait qu'une
petite partie des données. Presque aucune table n'a de clé étrangère avec
suppression en cascade vers le compte, donc tout ce qui n'était pas listé à
la main restait en base : bibliothèque et fichiers, jetons Notion et Google,
temps d'écran, rappels, réponses aux QCM, etc. Google Play et la loi
tunisienne 2004-63 exigent de supprimer les données liées au compte.

Règle, à appliquer sans que Bourama ait à la répéter : chaque fois qu'on
crée une table, une colonne ou un fichier de stockage qui contient une
donnée d'un utilisateur (colonne `user_id`, `owner_id`, `proprietaire_id`,
`etudiant_id`, `auteur_id`, etc.), dans la même livraison :
1. l'ajouter à `core/purge_compte.py` (liste `_TABLES_SIMPLES`, ou une étape
   dédiée si des fichiers ou des liens sans cascade sont en jeu) ;
2. l'ajouter à l'export `exporter_mes_donnees` dans `api/profiles.py` ;
3. préférer `ON DELETE CASCADE` vers `auth.users` dans la migration, et ne
   jamais créer de clé étrangère sans cascade vers un compte : elle bloque la
   suppression (erreur `PROFIL_FERMETURE_PARTIELLE`) ;
4. vérifier le schéma réel de la base (clés étrangères et colonnes), pas
   seulement le code : le code ne montre pas les colonnes de façon fiable ;
5. si la donnée est volontairement gardée (comme `journal_actions`, gardé
   pour la sécurité), le dire dans la politique de confidentialité.

Aucune table liée à un compte ne doit être livrée sans passer par ces points.

## Documentation : toujours à jour, toujours rangée, toujours traduite

Décision de Bourama du 4 novembre 2026. Cette règle est obligatoire : l'appliquer à chaque fois, sans demander et sans attendre qu'il la répète.

- **Toujours à jour.** Dès que le code, un comportement, une configuration ou une décision change, mettre à jour la documentation concernée dans la même modification.
- **Jamais de bazar.** Ne jamais déposer un fichier Markdown en vrac à la racine du dépôt. Tout nouveau document va dans `docs/`, ou dans un sous-dossier thématique (par exemple `docs/chantiers/`, `docs/specs/`) quand un sujet grossit. Créer un nouveau document ou un nouveau dossier dès que cela rend les choses plus claires, sans demander.
- **Toujours rangée.** Chaque nouveau document est ajouté à l'index de `docs/README.md` et `docs/README.fr.md` dans la même modification. Quand on modifie un ancien document encore à la racine (voir cet index), le déplacer dans `docs/` et corriger toutes ses références, dans les commentaires de code et dans les autres documents.
- **Toujours traduite.** Chaque document existe en anglais (par défaut, `.md`) et en français (`.fr.md`), avec la ligne de choix de langue en tête des deux. Mettre à jour les deux versions ensemble, jamais une seule.
- Seuls `README`, `CLAUDE` et leurs versions `.fr.md` restent à la racine.
- Ne jamais écrire de secret, de jeton ou de mot de passe dans la documentation.


### Documentation opérationnelle à conserver près de sa source

- Ne pas déplacer `skills_plateforme/<slug>/SKILL.md` ni `SKILL.fr.md`. Le script `scripts/synchroniser_skills_plateforme.py` lit les compétences depuis cette structure exacte pour publier les instructions utilisées à l'exécution.
- Ne pas déplacer `LISEZ_MOI_NE_JAMAIS_REUTILISER.md` ni son compagnon français hors de `_desactive_programme/` et `_desactive_roles_hierarchie/`. Ce sont des marqueurs de sécurité placés près du code désactivé ; ils doivent y rester.

## Tout texte visible doit exister en anglais, sinon le travail n'est pas fini

Ordre de Bourama du 7 novembre 2026. C'est une règle, pas une question : ne jamais demander s'il faut traduire.

- Tout texte qu'une personne peut lire existe en anglais comme en français : libellés de l'interface, données de catalogue (noms, descriptions, textes d'effets), textes préremplis dans un champ et envoyés à un modèle, messages d'erreur, et documentation.
- Les textes de catalogue et de données portent leur version anglaise à côté du français (par exemple `descriptionEn`), et l'écran choisit selon la langue réglée dans les paramètres. Les erreurs du serveur passent par un code stable avec un message français et un message anglais (`core/erreurs.py` et `lib/erreurs.ts`).
- Si un texte vit dans Supabase, ajouter aussi sa version anglaise là-bas.
- Une tâche qui ajoute ou change un texte visible sans sa version anglaise n'est pas terminée.
