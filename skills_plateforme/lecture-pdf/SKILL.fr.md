> [English version](./SKILL.md) · **Version française**

---
name: "Lecture de PDF"
description: "Méthode officielle Classinus pour lire un PDF joint ou donné par lien : regarder sa taille d'abord, chercher dans un long document, lire par pages, gérer scans et tableaux. À lire avant de répondre à une question sur un PDF."
---

# Lecture de PDF

À utiliser quand l'utilisateur pose une question sur un PDF (joint ou en ligne), veut un résumé, une citation ou des données. Pour créer ou modifier un PDF, utilise le skill Documents PDF.

## 1. Regarder avant de lire

Les fichiers joints ne sont pas lus automatiquement. Le message ne montre que leur nom, leur type, leur taille et leur nombre de pages, avec le vrai lien entre crochets après « Lien réel du fichier ». N'invente jamais ce lien.

Commence par `lire_document_conversation` en mode `infos` : type, taille, nombre de pages. Cela ne coûte rien et t'indique comment lire la suite.

## 2. Choisir le bon mode

- **Document court (quelques pages)** : mode `texte`.
- **Document long, question sur un sujet** : mode `recherche` avec le mot ou l'expression. Il renvoie les passages avec leur page. Utilise ensuite le mode `pages` avec `debut_page` et `fin_page` autour des meilleurs résultats.
- **L'utilisateur nomme une page, un chapitre ou une section** : mode `pages` sur cette plage.
- **L'utilisateur veut les données d'un tableau (relevé, bulletin, facture)** : mode `tableaux` avec `debut_page` et `fin_page`. Il renvoie des tableaux Markdown.
- **Résumé d'un long document entier** : lis-le dans l'ordre, tranche par tranche. Quand une réponse t'indique de rappeler l'outil avec un nouveau `debut_page` ou `debut_caractere`, fais-le avant de conclure. Si tu t'arrêtes avant la fin, dis exactement quelles pages tu as lues.

## 3. Pages scannées

Une page sans texte natif est lue par reconnaissance de texte, seulement quand tu le demandes, et la qualité peut varier. Si le résultat est vide ou illisible, dis-le, dis quelles pages sont concernées, et ne devine pas le contenu.

## 4. Tableaux, figures et chiffres

L'extraction de texte simple aplatit les tableaux : utilise le mode `tableaux` pour les obtenir sous forme de tableaux. Il ne marche que sur les pages à texte natif, jamais sur un scan ; pour une page scannée, lis-la avec le mode `pages` et dis que la structure du tableau peut être perdue. Cite les chiffres exactement comme écrits et donne la page. Pour calculer, convertir ou tracer à partir d'un tableau, importe le fichier dans le bac à sable (`gerer_execution_code`, action `importer_fichier`) et extrais-le avec `pdfplumber`, après avoir vérifié qu'il est installé.

## 5. PDF sur le web

Pour un PDF donné par lien (non joint), utilise `lire_document_externe` avec l'`url`, puis `a_partir_du_caractere` pour continuer et `rechercher` pour trouver un mot. La même logique tranche par tranche s'applique.

## 6. Répondre

- Donne le numéro de page avec chaque fait tiré du document.
- Sépare ce que dit le document de tes propres commentaires.
- Si le document est illisible, protégé ou ne contient pas la réponse, dis-le clairement. Ne comble jamais le vide de mémoire comme si cela venait du document.
- Pour les autres types de fichiers (vidéo, audio, archive, tableur), vois le skill Fichiers joints.
