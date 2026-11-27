# Chantier : page bambara (Maame), partie serveur

Dernière mise à jour : 27/11/2026. Branche de travail : staging. Statut : en cours. Le détail complet (décisions de Bourama, journal, ce qui a été fait côté page) est dans `chantiers/page-bambara-messages-audio/` du dépôt classinus-frontend.

## Où est la partie serveur
- `core/outils_page_bambara.py` : outils gardés pour la page (recherche web, génération visuelle, mémoire) et filtre par client `page_bambara`.
- `core/prompt_voix_bambara.py` : consignes bambara oral (`consignes_page`, notes A à D, `NOTE_PAGE_OUTILS`), `est_client_voix_bambara` et `est_client_page_bambara`.
- `core/mcp_tools.py` (filtre du catalogue par client) et `core/main.py` (outils toujours donnés à l'IA).
- Le serveur tourne sur Coolify (pas sur Railway) : c'est là que sont les journaux.

## Constat du 27/11 sur les images qui s'affichaient toutes seules
`_extraire_fichiers_generes` (`core/execution_outils.py`) annonce comme « fichier généré » toute adresse d'image trouvée dans le résultat d'un outil. Depuis que les outils de recherche n'envoient plus d'évènements `images` et `videos`, leurs miniatures (YouTube comprises) passent par ce chemin. La page filtre côté frontend (seul `generer_image` compte). Le serveur peut aussi les exclure, ce qui corrigerait peut-être le chat normal ; non vérifié.

## Point ouvert : « pourquoi l'IA dit ne pas pouvoir générer d'image ? »
- `generer_image` est autorisé sur la page (`OUTILS_GENERATION_VISUELLE`), mais `est_client_voix_bambara("page_bambara")` est faux : la liste `OUTILS_TOUJOURS_VOIX_BAMBARA` (recherche) n'est donc pas appliquée à la page, et `generer_image` n'est dans aucune liste « toujours donnée ».
- Hypothèse non vérifiée : l'IA ne voit pas `generer_image` dans sa liste d'outils et ne pense pas à passer par `demander_outils`.
- À faire : lire les journaux Coolify (ligne « Outils envoyés au LLM » pour `page_bambara`), puis corriger : donner `generer_image` à la page à chaque message, et dire à l'IA dans `NOTE_PAGE_OUTILS` qu'elle sait créer des images.
