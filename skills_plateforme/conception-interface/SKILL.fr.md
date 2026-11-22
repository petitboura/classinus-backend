> [English version](./SKILL.md) · **Version française**

---
name: "Conception d'interface"
description: "Méthode officielle Classinus pour concevoir une page web, un site ou une interface d'application avec un vrai parti pris visuel plutôt qu'un modèle générique. À lire avant d'écrire du HTML, du CSS ou du JavaScript pour une page, un site, un tableau de bord ou un petit outil."
---

# Conception d'interface

À utiliser quand l'utilisateur veut une page web, une page d'accueil, un site, un tableau de bord, un écran d'application ou un petit outil réalisé en HTML, CSS et JavaScript. Ne l'utilise pas pour un court extrait de code que tu expliques seulement dans le chat.

## 1. Cadrer avant de coder

S'il manque quelque chose d'essentiel (but, public, langue, contenu disponible), pose une seule question courte. Sinon, énonce tes hypothèses en une ligne et construis. Le vrai contenu vaut mieux que des textes provisoires : utilise les textes, noms et chiffres de l'utilisateur, dans sa langue. N'utilise jamais de faux texte du type lorem ipsum.

## 2. Choisir une direction et s'y tenir

Choisis une direction visuelle claire (éditoriale, calme, ludique, technique, audacieuse...) et applique-la partout. Un résultat générique est un résultat où rien n'a été choisi : dégradés violets par défaut, cartes arrondies identiques, un titre centré sur une vague accroche.

- **Couleur** : une couleur dominante, un accent, des neutres teintés plutôt que du gris pur. Définis-les une seule fois comme variables CSS.
- **Typographie** : deux familles au plus (une pour les titres, une pour le texte), une échelle claire avec un fort contraste entre les niveaux, une longueur de ligne confortable (environ 60 à 75 caractères) et un bon interligne. Donne toujours une liste de polices de secours, car une police qui ne se charge pas ne doit pas casser la mise en page.
- **Espace** : une seule échelle d'espacements (multiples de 4 ou 8 px), des marges généreuses, des alignements cohérents.
- **Détail** : un élément mémorable (une forme, une texture, une disposition inhabituelle) plutôt que dix décorations.

## 3. Liste de contrôle qualité

- **Adaptatif** : conçois d'abord pour un téléphone étroit (environ 360 px), puis pour les grands écrans. Inclus `<meta name="viewport" content="width=device-width, initial-scale=1">`. Aucun défilement horizontal. Zones tactiles d'au moins 44 px.
- **Accessible** : HTML sémantique (`header`, `main`, `nav`, vrais éléments `button`), contraste du texte d'au moins 4,5:1, focus visible, texte alternatif sur les images, étiquettes sur les champs, attribut `lang`.
- **Mouvement** : transitions courtes (150 à 300 ms) quand quelque chose s'ouvre, se ferme ou change. Rien n'apparaît ni ne disparaît brutalement. Respecte `prefers-reduced-motion`.
- **États** : conçois les états de chargement, de vide et d'erreur. Une zone blanche est un bug.
- **Textes prêts à traduire** : si la page peut être multilingue, garde tous les textes visibles dans un seul objet ou dictionnaire, pas éparpillés dans le code.
- **Mode sombre** : quand c'est pertinent, change les variables CSS avec `prefers-color-scheme`.
- **Images** : n'invente jamais de lien d'image. Utilise du SVG intégré, des formes CSS, ou des fichiers fournis par l'utilisateur.
- **Dépendances** : préfère du HTML, du CSS et du JavaScript simples. Si une bibliothèque est vraiment nécessaire, dis laquelle et pourquoi.

## 4. Livrer

Mets le point d'entrée dans `index.html` à la racine et utilise des chemins relatifs.

- Code source à télécharger (un ou plusieurs fichiers) : `generer_code` avec `nom_projet` et `fichiers`, un dictionnaire `{chemin: contenu}`. Un seul fichier est renvoyé directement, plusieurs deviennent un zip.
- Site statique en zip à héberger ailleurs : `generer_site_zip`, mêmes paramètres.
- Lien en ligne : `deployer_site`, mêmes paramètres, seulement si l'outil est disponible. Sinon, dis-le et propose le zip.

Tu ne peux pas voir la page rendue sauf si tu l'as vraiment ouverte. Relis donc ton code pour repérer les chemins cassés, les balises non fermées et les textes alternatifs manquants, et dis que tu ne l'as pas vue.

Termine par une phrase sur les choix de design et propose un ou deux ajustements concrets.
