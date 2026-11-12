# Test des voix bambara (dossier isolé)

[English version](TEST_BOUCHE_BAMBARA.md) · **Version française**

Dossier temporaire `bambara-bouche/`, isolé du reste du backend (aucun code existant modifié). Même principe que `bambara-ecoute/` : un dossier, un déploiement qui sert à la fois la page de test et les voix. À supprimer après les tests.

## Rôle

Un petit serveur avec une seule page de test. On écrit une phrase en bambara et on écoute chaque voix, une carte par voix, ou toutes à la suite avec « Tout écouter ». Chaque carte indique le statut de licence du modèle et si sa fiche le dit expérimental. La page et les voix étant servies par la même adresse, il n'y a ni problème de CORS ni de contenu mixte.

## Voix

| Id | Modèle | Locuteurs | Statut de licence (lu sur la fiche du modèle) |
|---|---|---|---|
| `bam_vits` | `RobotsMali/bam-vits` | 20 | Non vérifié. La fiche le décrit comme un point de contrôle de recherche très peu entraîné. |
| `ekodi_femme` | `ynnov/ekodi-bambara-tts-female` | 1 | La fiche annonce Apache 2.0, mais le modèle a la même architecture et la même taille que MMS (non commercial) : à confirmer avant la production. Vitesse 0,82 comme la fiche le conseille. |
| `mms_meta` | `facebook/mms-tts-bam` | 1 | CC BY-NC 4.0 : usage non commercial seulement, référence de comparaison. |
| `bam_fintech` | `RobotsMali/bam-vits-fintech` | 1 | CC BY 4.0 sur la fiche. Même famille que `bam_vits`, réentraînée sur des enregistrements propres d'un seul locuteur; reste un point de contrôle de recherche très peu entraîné. |
| `mms_sudoping01` | `sudoping01/bambara-tts` | 1 | CC BY-NC 4.0 : usage non commercial seulement, test uniquement. |

`bam_vits` reste pour comparaison mais n'est pas une voix utile après mesure : chaque enregistrement porte un motif fixe de 256 échantillons (un bourdonnement à 86 Hz et ses multiples) qui ne dépend ni du texte, ni du locuteur, ni du réglage du bruit; le défaut est dans le décodeur du modèle. Les modèles sur demande d'accès (`MALIBA-AI/bambara-tts`, `RobotsMali/Wuro`) ne sont pas au catalogue tant que l'accès n'est pas accordé. Ajouter une voix revient à ajouter une entrée dans `VOIX` de `voix.py`. Les statuts de licence sont ceux des fiches, pas un avis juridique.

## Réglages (variables d'environnement)

- `PORT` (8000 par défaut).
- `VOIX_ACTIVES` : identifiants de voix séparés par des virgules, toutes si absente.
- `TEXTE_MAX` (600 par défaut) : longueur maximale du texte en caractères.
- `SYNTHESES_MAX` (1 par défaut) : synthèses simultanées.
- `BRUIT_SCALE` (0,667 par défaut, entre 0 et 1) : hasard que VITS ajoute à chaque synthèse (le défaut du modèle). `BRUIT_DUREE` (0,8 par défaut) : pareil pour le rythme.
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

## Diagnostic du bourdonnement

Un bourdonnement constant à 86 Hz (la cadence interne du modèle, 22050/256) qui ne change ni avec le locuteur ni avec le réglage du bruit indique des poids du modèle non chargés. `transformers` est fixé à 5.9.0, la version avec laquelle la fiche du modèle a été testée. Ouvrir `/etat` : chaque voix indique `nb_manquantes` (nombre de poids absents du fichier de voix, doit valoir 0) et `manquantes` (les premiers noms). La même liste est écrite dans les logs en avertissement.
