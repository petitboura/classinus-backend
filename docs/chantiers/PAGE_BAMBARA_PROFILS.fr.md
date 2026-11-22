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

## Parcours d'inscription vocal (22 novembre 2026)

Le bouton `+` du panneau profil n'ouvre plus de champs écrits : il lance un parcours d'inscription plein écran fait uniquement de voix et d'images (frontend `components/bambara/ParcoursInscriptionBambara.tsx`, logique dans `lib/useParcoursBambara.ts`).

1. **Le nom.** Une voix demande le nom, la personne le dit, Soloni le transcrit, et la personne peut réécouter sa propre voix ainsi que la voix de Classinus qui dit ce nom (synthèse vocale), pour entendre ce que ça donnera quand c'est Classinus qui le dira.
2. **Femme ou homme.** Deux grandes images à toucher, sans texte.
3. **Présentation (facultative).** La personne peut dire quelques mots sur elle, ou passer avec une flèche.

À chaque étape une voix explique quoi faire. **Aucune de ces phrases n'est écrite dans le code** : elles sont lues par la synthèse vocale depuis la table Supabase `bambara_parcours_textes`, écrite par l'équipe. Une phrase absente est sautée et l'étape se joue sans consigne vocale.

| Clé | Quand elle est lue |
| --- | --- |
| `nom_demande` | Première étape, pour demander le nom. |
| `nom_reecoute` | Une fois le nom transcrit et dit par Classinus, pour expliquer comment réécouter, valider ou recommencer. |
| `genre_demande` | Deuxième étape, pour demander de choisir femme ou homme. |
| `presentation_demande` | Troisième étape, pour inviter à parler de soi (facultatif). |
| `fin` | Une fois le profil enregistré. |

Table `bambara_parcours_textes` : `cle`, `langue` (`bm` pour le bambara, la langue de la voix), `texte` (ce que la voix lit), `texte_fr` et `texte_en` (le sens, pour l'équipe, jamais lus), `actif`. Les lignes s'ajoutent et se modifient dans Supabase, sans déploiement.

Stockage : `bambara_profils` reçoit `genre` (`femme` ou `homme`) et `presentation` (2000 caractères au plus). Le nom dit à voix haute est rangé dans `prenom` et `nom` reste vide (la contrainte accepte maintenant de 0 à 60 caractères). Migration : `migrations/2026_11_22_bambara_parcours_inscription.sql`. Les nouvelles colonnes suivent le profil, donc la purge du compte et l'export des données les couvrent déjà.

Routes : `POST /api/bambara/profils/parcours` (nom, `genre`, `presentation` facultative) et `GET /api/bambara/parcours/textes?langue=bm`. Nouveaux codes d'erreur `BAMBARA_NOM_PARLE_INVALIDE`, `BAMBARA_PROFIL_GENRE_INVALIDE`, `BAMBARA_PRESENTATION_INVALIDE`, en français et en anglais. Tests : `test_bambara_parcours.py`.
