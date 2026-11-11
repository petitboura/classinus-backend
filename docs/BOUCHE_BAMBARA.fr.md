# Voix bambara (« bouche » de test)

[English version](BOUCHE_BAMBARA.md) · **Version française**

Statut : outil de test sur la branche `feat/bouche-bambara`, non déployé, non relié au chat. Demandé par Bourama le 12 novembre 2026 pour comparer à l'oreille des voix de synthèse vocale bambara avant d'en choisir une pour Classinus.

## De quoi il s'agit

Un service séparé qui transforme un texte bambara en fichier WAV, plus un relais dans le backend principal pour qu'un administrateur l'utilise depuis une page de test du frontend (`/dev-demo-bouche`).

```
Navigateur (admin) -> POST /api/bouche/synthese (backend principal, api/bouche.py)
                   -> POST /synthese (service bouche, api/main_bouche.py, jeton interne)
                   -> core/bouche_bambara.py -> modèle de voix -> WAV
```

Les voix tournent sur processeur seul. PyTorch et Transformers n'existent que dans le service séparé (`Dockerfile.bouche`, `requirements-bouche.txt`), jamais dans l'image du backend principal. C'est le même modèle que le service de montage vidéo.

## Fichiers

- `core/bouche_bambara.py` : catalogue des voix (`VOIX`), validation des demandes, chargement des modèles au premier usage, encodage WAV.
- `api/main_bouche.py` : le service séparé (`/sante`, `/voix`, `/synthese`). Toutes les routes sauf `/sante` vérifient le jeton interne (`SUPABASE_SECRET`).
- `api/bouche.py` : relais réservé aux administrateurs dans le backend principal (`GET /api/bouche/voix`, `POST /api/bouche/synthese`).
- `Dockerfile.bouche`, `requirements-bouche.txt` : construction du service séparé.
- `tests/test_bouche_bambara.py` : tests hors ligne (aucun modèle téléchargé, PyTorch inutile).

## Voix du catalogue

| Id | Modèle | Locuteurs | Statut de licence (lu sur la fiche du modèle) |
|---|---|---|---|
| `bam_vits` | `RobotsMali/bam-vits` | 20 | Non vérifié. La fiche le décrit comme un point de contrôle de recherche très peu entraîné. |
| `mms_sudoping01` | `sudoping01/bambara-tts` | 1 | CC BY-NC 4.0 : usage non commercial seulement. Test uniquement, jamais dans le produit payant. |

La voix de femme `ekodi` (`ynnov/ekodi-bambara-tts-female`) n'est pas encore au catalogue : sa fiche n'a pas pu être lue, donc sa méthode de chargement et sa licence ne sont pas vérifiées. Ajouter une voix revient à ajouter une entrée dans `VOIX` une fois sa fiche lue.

Les statuts de licence sont ceux des fiches de modèles, pas un avis juridique. À vérifier un par un avant toute mise en production.

## Configuration

Service séparé :

- `SUPABASE_SECRET` : le même jeton interne que le service principal.
- `BOUCHE_VOIX_ACTIVES` (facultatif) : identifiants de voix séparés par des virgules. Toutes les voix si absente.
- `BOUCHE_TEXTE_MAX` (facultatif, 600 par défaut) : longueur maximale du texte en caractères.
- `BOUCHE_SYNTHESES_MAX` (facultatif, 1 par défaut) : nombre de synthèses simultanées.
- `HF_HOME` (fixée dans le Dockerfile à `/data/huggingface`) : dossier où les poids des modèles sont gardés. Y brancher un volume évite de les retélécharger à chaque redémarrage.

Service principal :

- `BOUCHE_URL` : adresse du service bouche sans chemin, par exemple `http://nom-du-service.railway.internal:8000`. Sans cette variable, la page de test répond « non branchée » et rien d'autre ne change.
- `BOUCHE_DELAI_S` (facultatif, 180 par défaut) : attente maximale d'une synthèse. Le premier usage d'une voix télécharge son modèle, donc il est plus lent.

## Données et suppression de compte

Rien n'est stocké : ni table, ni fichier. Le texte envoyé n'est pas conservé. Aucun changement n'est nécessaire dans `core/purge_compte.py` ni dans l'export de `api/profiles.py`.

## Limites connues

- Rien n'a été lancé avec les vrais modèles dans l'environnement de développement (pas d'accès à Hugging Face). Les tests utilisent de faux modèles. Le premier vrai essai doit être vérifié à l'oreille et dans les journaux du service.
- `bam_vits` passe le texte en minuscules avant la synthèse, car sa fiche indique que les textes d'entraînement étaient en minuscules. Comparer avec et sans si le résultat sonne mal.
- La qualité se juge à l'oreille, idéalement par un locuteur bambara. Il n'existe aucune note automatique.
