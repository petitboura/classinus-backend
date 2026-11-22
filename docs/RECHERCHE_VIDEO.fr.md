# Recherche de vidéos dans Classinus

Le moteur de recherche vidéo est défini dans `core/recherche_video.py`.

## Sources et ordre d'utilisation

1. **YouTube Data API v3** : source prioritaire, avec les titres, chaînes,
   miniatures et durées quand elles sont disponibles.
2. **Serper Videos** : complète les résultats manquants avec Google Videos.
3. **SerpApi Google Videos** : autre moteur Google Videos en secours.
4. **SearchApi Google Videos** : troisième moteur Google Videos.
5. **Tavily** : dernier recours pour compléter les liens YouTube.

Les fournisseurs payants ne sont appelés que si les sources précédentes ne
remplissent pas le nombre demandé. Les clés manquantes sont ignorées.
Les fournisseurs sont interrogés séquentiellement pour éviter des appels
inutiles et limiter les coûts.

Google Videos peut retourner des vidéos hébergées sur YouTube, Vimeo,
Dailymotion, TikTok, Facebook et d'autres sites indexés. Les résultats
restent des liens vers leur plateforme d'origine : seul YouTube bénéficie
du lecteur intégré actuel de Classinus ; les autres plateformes s'ouvrent
sur leur site.

## Variables d'environnement

| Variable | Utilisation |
| --- | --- |
| `YOUTUBE_API_KEY` | YouTube Data API v3 |
| `GOOGLE_API_KEY` | Repli pour YouTube si `YOUTUBE_API_KEY` est absente |
| `SERPER_API_KEY` | Serper Videos |
| `SERPAPI_API_KEY` | SerpApi Google Videos |
| `SEARCHAPI_API_KEY` | SearchApi Google Videos |
| `TAVILY_API_KEY` | Secours Tavily |
| `RECHERCHE_VIDEO_MEMOIRE_SECONDES` | Cache en secondes, 86 400 par défaut |
| `RECHERCHE_VIDEO_MEMOIRE_TAILLE` | Nombre de requêtes en cache, 500 par défaut |
| `RECHERCHE_VIDEO_PAUSE_QUOTA_SECONDES` | Pause après quota YouTube, 3 600 par défaut |
| `RECHERCHE_VIDEO_PAUSE_CLE_SECONDES` | Pause après clé YouTube refusée, 600 par défaut |

Les clés Serper, SerpApi et SearchApi sont les mêmes que celles déjà utilisées
par la recherche d'images. Aucune nouvelle clé n'est nécessaire si elles sont
déjà configurées dans l'environnement du backend.

## Nombre de résultats et pagination

- 30 résultats par recherche par défaut.
- Maximum technique : 50 résultats par page.
- Le paramètre `page` permet de demander les pages suivantes.
- Le cache distingue la requête, le nombre de résultats et la page.
- Les URLs sont dédupliquées avant le retour.

L'outil renvoie `videos_trouvees`, et non `videos` : l'IA garde donc le
contrôle et choisit les vidéos réellement pertinentes à afficher. Aucune
galerie automatique de tous les résultats n'est déclenchée.

## Affichage progressif (page bambara)

Le 22 novembre 2026, `rechercher_videos` a reçu un paramètre facultatif `sur_lot`,
appelé avec le nom de la source et ses nouvelles vidéos dès qu'une source a
répondu. Sur la page bambara, chaque lot part alors à un petit LLM de tri puis à
l'écran (événement `bloc_media`, `genre` = `videos`), sans attendre les sources
suivantes. L'ordre d'économie ne change pas : une source payante n'est toujours
appelée que si les précédentes n'ont pas rempli la page. Le détail est dans
`RECHERCHE_IMAGE.fr.md`, section « Affichage progressif (page bambara) ». Sans
`sur_lot`, le comportement est exactement celui d'avant.

## État des tests

Les tests unitaires hors réseau sont dans
`tests/test_recherche_video_multisources.py`. Les clés API et les services
externes doivent encore être vérifiés dans l'environnement Railway.