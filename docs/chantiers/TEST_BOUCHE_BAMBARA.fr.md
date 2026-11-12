# Test des voix bambara (dossier isolé)

[English version](TEST_BOUCHE_BAMBARA.md) · **Version française**

Dossier temporaire `bambara-bouche/`, isolé du reste du backend (aucun code existant modifié). Même principe que `bambara-ecoute/` : un dossier, un déploiement qui sert à la fois la page de test et les voix. À supprimer après les tests.

## Rôle

Un petit serveur avec une seule page de test. On écrit une phrase en bambara et on écoute chaque voix, une carte par voix, ou toutes à la suite avec « Tout écouter ». Chaque carte indique le statut de licence du modèle et si sa fiche le dit expérimental. La page et les voix étant servies par la même adresse, il n'y a ni problème de CORS ni de contenu mixte.

## Voix

| Id | Modèle | Locuteurs | Statut de licence (lu sur la fiche du modèle) |
|---|---|---|---|
| `bam_vits` | `RobotsMali/bam-vits` | 20 | Non vérifié. La fiche le décrit comme un point de contrôle de recherche très peu entraîné. |
| `mms_sudoping01` | `sudoping01/bambara-tts` | 1 | CC BY-NC 4.0 : usage non commercial seulement, test uniquement. |

La voix de femme `ekodi` n'est pas au catalogue : sa fiche n'a pas pu être lue, donc sa méthode de chargement et sa licence ne sont pas vérifiées. Ajouter une voix revient à ajouter une entrée dans `VOIX` de `voix.py`. Les statuts de licence sont ceux des fiches, pas un avis juridique.

## Réglages (variables d'environnement)

- `PORT` (8000 par défaut).
- `VOIX_ACTIVES` : identifiants de voix séparés par des virgules, toutes si absente.
- `TEXTE_MAX` (600 par défaut) : longueur maximale du texte en caractères.
- `SYNTHESES_MAX` (1 par défaut) : synthèses simultanées.
- `BRUIT_SCALE` (0,3 par défaut, entre 0 et 1) : hasard que VITS ajoute à chaque synthèse (défaut du modèle : 0,667). À baisser si la voix est bruitée; une voix peu entraînée transforme ce hasard en bruit audible. `BRUIT_DUREE` (0,8 par défaut) : pareil pour le rythme.
- `PRECHARGER` (1 par défaut) : mettre 0 pour charger chaque voix à son premier usage plutôt qu'au démarrage.
- `TEST_ACCESS_TOKEN` : si défini, `/voix` et `/synthese` l'exigent. Ouvrir la page avec `?token=VALEUR`.
- `HF_HOME` (fixé à `/data/hf` dans le Dockerfile) : dossier où les poids des modèles sont gardés. Monter un volume sur `/data`.

## Déployer sur Coolify

Build pack Dockerfile, dossier de base `/bambara-bouche`, port 8000, domaine commençant par `https://` (pour que Coolify demande un vrai certificat), volume persistant sur `/data`. Chemin de contrôle de santé : `/etat`.

## Limites

- Rien n'a été lancé avec les vrais modèles là où ceci a été écrit (pas d'accès à Hugging Face). Les tests utilisent de faux modèles. Vérifier le premier vrai essai à l'oreille et dans les journaux ; un échec de chargement s'affiche sur la page.
- `bam_vits` passe le texte en minuscules avant la synthèse, car sa fiche indique que les textes d'entraînement étaient en minuscules. Comparer avec et sans si le résultat sonne mal.
- Ni compte, ni base de données, rien n'est conservé. Toute personne qui a l'adresse peut utiliser les voix, sauf si `TEST_ACCESS_TOKEN` est défini.

## Lancer les tests

Depuis le dossier : `python3 -m unittest test_app`.
