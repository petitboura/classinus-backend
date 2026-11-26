# Ligne d'outils et notes de l'IA (l'outil `commenter`)

[English version](LIGNE_OUTILS_COMMENTAIRE.md) · **Version française**

Demande du 25 novembre 2026. Dans le chat, l'activité des outils tient sur une seule ligne repliée où chaque nouvelle ligne remplace la précédente, comme une roue qui tourne vers le haut. L'IA peut aussi glisser une courte note à l'utilisateur entre ses appels d'outils, affichée comme sa propre ligne avec une icône point. L'affichage se trouve dans le dépôt frontend (`OutilResultatBulle.tsx`). Cette page décrit la partie backend.

## L'outil interne `commenter`

- Défini dans `core/routage_outils.py` (`_outil_commenter`, `_separer_appels_commenter`). Comme `garder_outils`, il n'est jamais routé vers `table_routage`, jamais compté parmi les appels d'outils du tour et jamais pris en compte par la détection de répétition.
- Ajouté dans `core/main.py`, après `demander_outils`, dès que des outils sont proposés. Non proposé au client vocal bambara, qui n'a pas de timeline à l'écran.
- La définition est fixe, donc le cache de prompt n'est pas cassé. Elle est écrite en anglais exprès : la note doit être écrite dans la langue du dernier message de l'utilisateur.
- Un seul paramètre, `texte`. Le texte est nettoyé par `nettoyer_commentaire` dans `core/libelles_activite_ia.py` (une ligne, sans balises ni crochets, sans tirets doubles, 240 caractères au plus). Une note inutilisable n'est pas montrée et le modèle est prévenu qu'elle a été ignorée.
- Plafond : `MAX_COMMENTAIRES_PAR_TOUR` notes par tour (`core/boucle_agent.py`). Au-delà, le modèle est prévenu de ne plus en écrire.

## Événements et persistance

- La boucle envoie un événement `commentaire` par note (`texte`, `id_appel`), sans `statut` ni `outil_resultat`. Le modèle reçoit une courte réponse synthétique et continue son travail.
- La note n'est pas traduite par le serveur de chat : l'IA l'écrit déjà dans la bonne langue.
- `_capturer_reponse` la garde dans `meta["segments"]` sous la forme `{"type": "commentaire", "texte": ...}`, dans l'ordre, pour que la ligne survive à la réouverture d'une conversation. Elle n'est jamais gardée dans `meta["outils"]`, puisqu'il n'y a rien à rejouer au modèle.

## Texte des lignes d'outils

Depuis le 26 novembre 2026, l'IA est invitée à écrire pour chaque outil un texte d'environ 15 mots (12 à 18), limité à `LONGUEUR_MAX_LIBELLE` caractères (`core/libelles_activite_ia.py`). La longueur des notes ne change pas.

Ce texte est obligatoire : la consigne le dit et le champ est requis dans le schéma envoyé au modèle, sauf pour les modèles servis par Groq, qui refuserait tout l'appel si le champ manquait. Si un modèle l'oublie quand même, le texte fixe habituel s'affiche.

## Tests

`test_commenter_outil.py` joue la vraie boucle avec un faux fournisseur : événement, réponse au modèle, plafond, persistance, nettoyage et définition fixe.
