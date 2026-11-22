# Page bambara : profils, historique et éléments gardés

[English version](PAGE_BAMBARA_PROFILS.md) · **Version française**

Ajouté le 18 novembre 2026 à la demande de Bourama, d'abord construit sur staging pour être amélioré ensuite. La page bambara (`/bambara` côté frontend) a maintenant une rangée de boutons en haut : nouveau profil, nouvelle conversation (un simple « + »), historique, et éléments gardés. Chaque vidéo et chaque image a aussi un cœur pour la garder.

## Ce qui est gardé

| Table | Contenu |
| --- | --- |
| `bambara_profils` | Une personne qui se sert du compte : nom et prénom, rien d'autre. |
| `bambara_conversations` | Une ligne par conversation, avec son premier message (texte écrit, ou seulement un indicateur « vocal »). |
| `bambara_audios` | Le premier vocal d'une conversation (WAV en base64, durée, barres de la bulle), gardé à part pour que la liste de l'historique reste légère. |
| `bambara_gardes` | Les vidéos et images gardées par une personne (genre, adresse, titre, miniature). |

Migration : `migrations/2026_11_18_page_bambara_profils_historique.sql`. Chaque table suit le compte avec `ON DELETE CASCADE`, a la sécurité par ligne activée sans règle (seul le backend lit et écrit), et fait partie de la purge du compte (`core/purge_compte.py`). Les conversations, profils et éléments gardés sont dans l'export des données ; l'audio n'y est pas, il est trop lourd.

Quand aucun profil n'est choisi, les conversations et éléments gardés appartiennent à un espace commun du compte (`profil_id` vide).

## Routes (`api/bambara_profils.py`, logique dans `core/bambara_profils.py`)

- `GET /api/bambara/profils`, `POST /api/bambara/profils` (nom, prénom ; 20 profils au maximum par compte).
- `GET /api/bambara/conversations?profil_id=` liste les 30 dernières conversations avec leur premier message.
- `PUT /api/bambara/conversations/{id}/premier-message` garde le premier message une seule fois ; le renvoyer ne change rien. L'audio est refusé au delà d'environ 1,5 Mo.
- `GET /api/bambara/conversations/{id}/audio` renvoie le premier vocal.
- `GET /api/bambara/gardes?profil_id=`, `POST /api/bambara/gardes`, `DELETE /api/bambara/gardes/{id}`. Garder deux fois le même élément renvoie la même ligne.

Les erreurs ont des codes stables `BAMBARA_*` avec messages français et anglais (`core/erreurs.py`, `lib/erreurs.ts` côté frontend). La page n'affiche jamais d'erreur à l'écran.

## Limites connues de cette première version

- L'audio est gardé dans la base (base64). Le passer dans un stockage de fichiers est le choix durable si le volume grossit.
- L'historique liste seulement les premiers messages. Rouvrir une ancienne conversation n'est pas construit.
- Tests : `test_bambara_profils.py`.
