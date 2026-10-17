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
