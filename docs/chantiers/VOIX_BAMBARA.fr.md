# Mode vocal bambara

[English version](VOIX_BAMBARA.md) · **Version française**

Statut : demandé par Bourama le 13 novembre 2026, branche `feat/voix-bambara-chaine`.

## Ce que ça fait

À l'activation du mode vocal, Classinus demande « bambara ou autre ? ». « Autre » garde le mode vocal actuel (Gemini Live), sans aucun changement. « Bambara » lance cette chaîne :

```
micro -> Soloni (transcrit seulement) -> texte -> IA de Classinus (chat) -> réponse -> voix Gemini -> haut-parleur
```

Deux services séparés font le travail audio, hors du backend principal : `bambara-ecoute/` (Soloni) et `bambara-bouche/` (voix Gemini). Le navigateur ne les appelle jamais directement : il passe par le relais `api/voix_bambara.py`, avec son jeton de compte.

## Routes (relais, `api/voix_bambara.py`)

- `GET /api/voix-bambara/etat` : `{"disponible": bool, "texte_max": int}`. `disponible` est vrai seulement si les deux adresses sont réglées. Le frontend ne propose le bambara que dans ce cas.
- `POST /api/voix-bambara/transcrire` : envoie l'enregistrement (champ `fichier`) à Soloni, renvoie `{"texte": ...}`.
- `POST /api/voix-bambara/synthese` : `{"texte": ...}` renvoie un WAV lu par la voix Gemini.

## Consignes données à l'IA

Le frontend envoie `client: "voix_bambara"` avec chaque message du mode bambara (même principe que `thonny`, voir `core/prompt_voix_bambara.py`). Le prompt reçoit alors deux notes, dans sa partie variable, et rien d'autre ne change :

1. Tout est du texte simple, aucun élément enrichi (fichier, lien, code, diagramme, fiche, QCM, image, tableau), puisque tout est lu à voix haute.
2. L'utilisateur comprend uniquement le bambara, ne sait ni lire ni écrire, peut seulement parler et écouter : l'IA répond en bambara, adapté à l'oral.

## Configuration (variables d'environnement du backend principal)

Rien n'est écrit en dur.

- `VOIX_BAMBARA_ECOUTE_URL` : adresse du service Soloni, sans chemin.
- `VOIX_BAMBARA_BOUCHE_URL` : adresse du service de la voix Gemini, sans chemin.
- `VOIX_BAMBARA_BOUCHE_TOKEN` (facultatif) : envoyé dans `X-Test-Token`, à régler comme `TEST_ACCESS_TOKEN` du service de voix.
- `VOIX_BAMBARA_VOIX` (facultatif) : identifiant de la voix, `gemini_tts` par défaut.
- `VOIX_BAMBARA_TEXTE_MAX` (facultatif, 600) : taille maximale d'un morceau lu. À régler comme `TEXTE_MAX` du service de voix.
- `VOIX_BAMBARA_AUDIO_MAX_MO` (facultatif, 10) : taille maximale d'un enregistrement.
- `VOIX_BAMBARA_DELAI_S` (facultatif, 120) : attente maximale d'un service.

Les deux services gardent leurs propres variables (voir `docs/chantiers/TEST_BOUCHE_BAMBARA.fr.md` et le dossier `bambara-ecoute/`). Le service de voix a besoin de `GOOGLE_API_KEY`.

## Données et suppression de compte

Rien n'est stocké : ni table, ni fichier. L'audio et le texte ne font que passer. Rien à ajouter à `core/purge_compte.py` ni à l'export de `api/profiles.py`.

## Limites connues

- Soloni n'a pas de jeton d'accès propre : son adresse ne doit pas être publiée, ou il faut le protéger au niveau du réseau.
- La qualité de la transcription et de la voix se juge à l'oreille, idéalement par un locuteur bambara. Aucun essai avec les vrais services n'a été fait pendant le développement : les tests utilisent de faux services.
- Le frontend de ce mode est décrit dans `docs/VOIX_BAMBARA.fr.md` du dépôt classinus-frontend.
