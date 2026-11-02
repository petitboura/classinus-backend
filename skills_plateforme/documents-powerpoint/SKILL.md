---
name: "Documents PowerPoint"
description: "Méthode officielle Classinus pour créer ou modifier une présentation PowerPoint (.pptx) lisible : format 16:9, une idée par diapositive, graphiques natifs, notes de l'orateur. À lire avant de produire un fichier .pptx."
---

# Présentations PowerPoint (.pptx)

À utiliser quand l'utilisateur veut un fichier PowerPoint, à créer ou à modifier. Pour un plan de présentation à lire dans le chat, ne fabrique pas de fichier.

## 1. Préparer le bac à sable

Travaille avec l'outil gerer_execution_code.

1. Vérifie la bibliothèque : `python -c "import pptx; print(pptx.__version__)"`.
2. Si elle manque : `pip install python-pptx`. Si l'installation échoue faute de réseau, appelle l'action network, puis demander_acces_reseau pour pypi.org si besoin. Si pip refuse à cause d'un environnement géré, crée un environnement virtuel : `python -m venv /home/user/venv` puis `/home/user/venv/bin/pip install python-pptx`.
3. Si rien ne marche, dis-le et propose l'outil simple generer_document_powerpoint (titre et texte seulement).

Limites : une commande dure 60 secondes au plus, run_command accepte 10000 caractères, un fichier ou un script ne dépasse pas 1 Mo. Les images embarquées comptent dans cette taille : réduis-les (Pillow, largeur 1600 px au plus, JPEG) avant de les insérer.

## 2. Construire la présentation

- Format 16:9 : `prs.slide_width = Inches(13.333)` et `prs.slide_height = Inches(7.5)`. Le modèle par défaut de python-pptx est en 4:3.
- Utilise la mise en page vide (`prs.slide_layouts[6]`) et place toi-même les zones de texte et les formes : les mises en page du modèle par défaut sont dessinées pour le 4:3 et se décalent en 16:9.
- Une idée par diapositive. Le titre dit la conclusion (8 mots au plus), pas le sujet. Environ 30 mots de corps au plus. Trois à cinq puces courtes, ou un visuel.
- Tailles : titre 32 à 40 pt, corps 18 à 24 pt, jamais sous 14 pt. Si le texte ne tient pas, coupe la diapositive en deux, ne réduis pas la police.
- Une palette : une couleur dominante, une couleur d'accent, du texte à fort contraste sur le fond. Une seule famille de police. Mêmes marges (0,6 pouce) et mêmes positions de titre sur toutes les diapositives.
- Diapositive d'ouverture (titre, sous-titre), une diapositive par idée, une conclusion avec la suite à donner. Pas de diapositive "Merci" vide.
- Graphiques natifs : `CategoryChartData` et `slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, ...)`, avec titre et légende lisibles. Un graphique natif reste modifiable par l'utilisateur, contrairement à une image.
- Images : seulement celles que l'utilisateur fournit ou qui servent le propos, jamais décoratives. Conserve les proportions.
- Notes de l'orateur quand c'est utile : `slide.notes_slide.notes_text_frame.text = "..."`.

## 3. Modifier une présentation existante

1. Copie le fichier joint dans le bac à sable avec importer_fichier (url_fichier : le lien réel indiqué après le fichier, jamais inventé).
2. Ouvre-le avec `Presentation(chemin)`, garde ses mises en page et son thème, et modifie seulement ce qui est demandé.
3. Enregistre sous un nouveau nom. L'original reste intact.

## 4. Vérifier avant de livrer

Tu ne peux pas voir le rendu dans ce bac à sable : vérifie par les mesures. Rouvre le fichier et, pour chaque diapositive, contrôle que chaque forme reste dans les limites de la diapositive (`left + width <= slide_width`, `top + height <= slide_height`), compte les mots, et signale celles qui dépassent 40 mots ou dont une forme déborde. Relis le texte pour les fautes. Dis honnêtement à l'utilisateur que tu n'as pas pu contrôler le rendu à l'œil si c'est le cas.

## 5. Livrer

Utilise l'action download_files avec path vers ce seul fichier. Si le fichier dépasse la limite de taille de téléchargement, dis-le. Termine par une phrase : le nombre de diapositives, le fil de la présentation et les choix de design.
