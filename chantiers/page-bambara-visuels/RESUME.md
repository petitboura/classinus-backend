# Page bambara : images et vidéos façon Google (côté backend)

- **Statut** : en cours (l'essentiel est dans staging ; une partie attend une décision de Bourama)
- **Dernière mise à jour** : 2026-11-27
- **Dépôts concernés** : classinus-backend ici ; le résumé complet est dans `classinus-frontend/chantiers/page-bambara-visuels/RESUME.md`
- **Branche(s)** : `staging` pour ce qui est fait ; `feature/galerie-images-multiples-sources` pour « l'affichage progressif », pas encore dans staging

## Le but, en langage clair
Sur la page bambara, l'utilisateur ne sait pas lire : l'écran ne montre que des images et des vidéos. Bourama veut beaucoup de résultats bien présentés, comme chez Google. Le détail de l'écran est côté frontend ; ici, c'est la recherche et les consignes données au modèle.

## Ce qui est déjà fait (dans staging)
- **Recherche d'images et de vidéos multi-sources** reprise de `feature/galerie-images-multiples-sources` (17 commits) : plusieurs sources en parallèle, pagination, provenance de chaque résultat. La cascade de staging (Wikimedia, Openverse, Serper, SerpApi, Pixabay, Pexels) est conservée, avec les nouvelles sources ajoutées dans l'ordre par défaut (`core/recherche_image.py`, `core/recherche_video.py`).
- **Consigne vidéo** (`core/outils_generation_media.py`) corrigée pour garder la règle du 08/11 : l'IA choisit ce qu'elle écrit, rien ne s'affiche tout seul ; test de garde `tests/verifier_recherche_media_choix_ia.py`.
- **Règle de quantité pour la page bambara seulement** : note C dans `core/prompt_voix_bambara.py` (`NOTE_PAGE_QUANTITE`, ajoutée par `consignes_page()`). Elle dit au modèle que la quantité compte autant que la qualité, que le tri sert à écarter le hors sujet et pas à élire les meilleurs, d'écrire les images à la suite sans ligne vide, et de rappeler l'outil avec `page=2` s'il en reste peu. Les consignes générales de `rechercher_image` et `rechercher_video` n'ont pas été changées (une première version générale a été annulée par un revert).

## Ce qui reste à faire
1. Décider du commit « Affichage progressif des images et videos sur la page bambara » (`82fceb5`, 22/11 au soir) : il ajoute `core/medias_progressifs.py` (environ 400 lignes) et modifie `core/execution_outils.py`, `core/outils_page_bambara.py`, `core/recherche_image.py` et `core/recherche_video.py`. Il n'est pas dans staging.
2. Vérifier que les clés d'API des nouvelles sources d'images sont dans les variables de staging (voir `docs/RECHERCHE_IMAGE.fr.md`) ; sans clé, la source est ignorée.
3. Essayer sur staging avec une demande simple (par exemple « montre-moi des images de la tour Eiffel ») pour voir combien d'images le modèle écrit réellement.

## Décisions prises par Bourama
- La règle « la quantité compte autant que la qualité » vaut surtout pour la page bambara, pas pour toute la plateforme.
- La galerie multi-sources est fusionnée dans staging pour toute la plateforme, en respectant ce qui était plus récent.

## Points ouverts
- Fusionner ou non « l'affichage progressif » (voir ci-dessus). La branche contient aussi une fusion de staging du 22/11 : ne pas la fusionner telle quelle sans comparer avec staging d'aujourd'hui.
- Limiter aussi la galerie multi-sources à la page bambara ? Question posée à Bourama, pas de réponse.
- Le test `test_voix_bambara.py` échoue déjà sur staging (module `construction_system_prompt` introuvable à l'import).

## Pour l'IA qui reprend ce chantier
- `git fetch`, puis compare `origin/staging` et `origin/feature/galerie-images-multiples-sources` avant d'agir.
- Pour lancer les tests de recherche : environnement Python isolé, variables Supabase factices et `PYTHONPATH=".:core"`.
- Ne change pas les consignes générales des outils de recherche pour y mettre une règle propre à la page bambara : place-la dans `core/prompt_voix_bambara.py`.
