# Page bambara : phrases proactives

[English version](PAGE_BAMBARA_PHRASES.md) · **Version française**

Ajouté le 22 novembre 2026 à la demande de Bourama, d'abord construit sur staging. La page bambara (`/bambara` côté frontend) restait muette tant que la personne ne parlait pas, et pendant qu'un outil travaillait rien ne se disait. La page parle maintenant d'elle même à six moments, pour que la personne ne reste jamais devant le silence. La personne ne sait pas lire : ces phrases sont dites à voix haute, jamais écrites à l'écran.

## Les six moments

| Moment (`moment`) | Quand elle passe |
| --- | --- |
| `accueil` | Quand la personne arrive sur la page. |
| `recherche_web` | Quand l'IA commence une recherche web. |
| `recherche_videos` | Quand l'IA commence à chercher ou à lire des vidéos. |
| `recherche_images` | Quand l'IA commence à chercher des images. |
| `creation_image` | Quand l'IA commence à créer une image. |
| `outil_lent` | Quand un outil prend du temps : après un délai, puis à chaque intervalle, tant qu'un outil travaille encore. |

Les outils de mémoire n'ont pas de phrase à eux, ils sont rapides. Chaque moment d'outil passe au plus une fois par demande, l'accueil une fois par visite, et seul `outil_lent` peut se répéter.

## Où vivent les textes (Supabase)

Rien n'est écrit dans le code : ni les phrases, ni les délais. Deux tables, communes à tous les comptes (aucune donnée de compte, donc rien à ajouter à la purge du compte ni à l'export). Migration : `migrations/2026_11_22_page_bambara_phrases_proactives.sql`. Les deux tables ont la sécurité par ligne activée sans règle : seul le backend lit et écrit.

| Table | Contenu |
| --- | --- |
| `bambara_phrases_proactives` | Une ligne par phrase : `moment`, `texte` (bambara, lu à voix haute), `texte_en` (traduction anglaise pour l'équipe), `actif`, et l'audio gardé (`audio_base64`, `audio_duree_ms`, `audio_empreinte`). |
| `bambara_phrases_reglages` | Une seule ligne : `delai_outil_lent_s` (6 par défaut) et `intervalle_outil_lent_s` (12 par défaut). |

Plusieurs phrases pour un même moment sont des variantes : la page en tire une au hasard et ne répète pas celle qui vient de passer quand il y en a plusieurs.

Pour ajouter une phrase, on ajoute une ligne. L'audio se fabrique tout seul :

```sql
insert into public.bambara_phrases_proactives (moment, texte, texte_en)
values ('accueil', '<phrase en bambara>', '<traduction anglaise>');

update public.bambara_phrases_reglages set delai_outil_lent_s = 6, intervalle_outil_lent_s = 12;
```

Pour retirer une phrase sans la supprimer, mettre `actif` à faux. La migration ne met aucune phrase : les textes bambara sont choisis et vérifiés par Bourama.

## Comment l'audio est fabriqué (la voix est une variable)

La voix est la même variable que le reste de la page, `VOIX_BAMBARA_VOIX` (`gemini_tts` par défaut, voir `docs/chantiers/VOIX_BAMBARA.fr.md`). Changer la variable change la voix de toutes les phrases.

L'audio n'est pas fabriqué à chaque visite. La première fois qu'une phrase est demandée, le serveur la fait lire une fois par le TTS (`api/voix_bambara.py`, fonction `synthetiser_texte`, aussi utilisée par la route de synthèse habituelle) et garde le fichier à côté du texte. `audio_empreinte` retient la voix et le texte avec lesquels il a été fabriqué :

- Si le texte ou la voix change, l'audio n'est plus valable et il est refait tout seul, en arrière plan. Un déclencheur de la base le vide aussi quand `texte` est modifié directement dans Supabase.
- Une phrase n'est proposée de nouveau qu'une fois son audio prêt avec la voix et le texte actuels.
- Une phrase qui échoue n'est pas retentée avant 60 secondes, et n'arrête jamais les autres.

## Routes (`api/bambara_phrases.py`, logique dans `core/phrases_bambara.py`)

- `GET /api/bambara/phrases` renvoie les phrases prêtes (`id`, `moment`, `duree_ms`, `version`), les délais (`reglages`) et `en_preparation`, le nombre de phrases dont l'audio est en cours de fabrication. L'audio n'est pas dans cette réponse, il est lourd. Si un audio manque, il est fabriqué en arrière plan après la réponse.
- `GET /api/bambara/phrases/{id}/audio?v={version}` renvoie le fichier WAV d'une phrase prête, avec `Cache-Control: private, max-age=31536000, immutable` : le navigateur le garde, et `v` change dès que la voix ou le texte change. Une phrase pas prête, ou fabriquée avec une autre voix, répond 404.

Nouveau code d'erreur, en français et en anglais (`core/erreurs.py`, `lib/erreurs.ts`) : `BAMBARA_PHRASE_INTROUVABLE`. Le frontend ne montre jamais d'erreur : une phrase qui ne peut pas jouer est sautée.

## Comment le frontend les joue (voir `docs/VOIX_BAMBARA.fr.md` du dépôt frontend)

- La page télécharge une variante par moment en arrière plan, l'accueil d'abord, une à la fois pour ne pas ralentir une connexion lente. La variante suivante est préparée dès qu'une phrase a passé.
- Une phrase n'est jamais coupée par l'arrivée de la réponse : la réponse attend la fin de la phrase qui parle. Seul un geste explicite de la personne (arrêter, nouvelle conversation, réécouter un message, lancer une vidéo, envoyer un message écrit) l'arrête.
- Les phrases ne se mélangent jamais : une seule parle à la fois, les autres attendent leur tour, et celles qui n'ont plus de raison d'être (l'outil a fini) sont retirées avant de commencer. Le micro est en pause pendant qu'une phrase parle.
- L'accueil est sauté, jamais retardé, si le navigateur n'autorise pas encore le son ou si la personne touche l'écran avant qu'il commence.

## Limites

- Aucune phrase n'est fournie : tant qu'aucune ligne n'est ajoutée dans Supabase, la page reste muette comme avant.
- La première visite après l'ajout d'une phrase ou un changement de voix peut ne pas avoir son audio (il se fabrique en arrière plan). La page redemande jusqu'à trois fois, à dix secondes d'écart.
- Certains navigateurs, surtout sur iPhone, n'autorisent le son qu'après un toucher : l'accueil peut ne pas passer.
- Aucun test n'a été fait avec le vrai service TTS pendant le développement. La migration Supabase n'a été appliquée que sur le projet de staging.

Tests : `python -m unittest test_phrases_bambara` (backend) et `npm run test:phrases-bambara` (frontend).
