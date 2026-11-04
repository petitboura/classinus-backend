> [English version](./SKILL.md) · **Version française**

---
name: "Documents Word"
description: "Méthode officielle Classinus pour créer ou modifier un document Word (.docx) propre : titres, listes, tableaux, pagination, mise en page A4. À lire avant de produire un fichier .docx."
---

# Documents Word (.docx)

À utiliser quand l'utilisateur veut un fichier Word, à créer ou à modifier. Pour un texte à lire dans le chat, ne fabrique pas de fichier.

## 1. Préparer le bac à sable

Travaille avec l'outil gerer_execution_code.

1. Vérifie la bibliothèque : `python -c "import docx; print(docx.__version__ if hasattr(docx, '__version__') else 'ok')"`.
2. Si elle manque, installe-la : `pip install python-docx`. Si l'installation échoue faute de réseau, appelle l'action network, puis demander_acces_reseau pour pypi.org si besoin. Si pip refuse à cause d'un environnement géré, crée un environnement virtuel : `python -m venv /home/user/venv` puis `/home/user/venv/bin/pip install python-docx`.
3. Si rien ne marche, dis-le à l'utilisateur et propose l'outil simple generer_document_word (titres et paragraphes seulement).

Limites à respecter : une commande dure 60 secondes au plus, run_command accepte 10000 caractères, un fichier ou un script ne dépasse pas 1 Mo. Pour un long document, écris le contenu dans un fichier de données (write_file, par exemple contenu.json) et garde un script court qui le lit.

## 2. Construire le document

- Page A4 avec marges de 2,5 cm : `section.page_width = Mm(210)`, `section.page_height = Mm(297)`, marges en Cm(2.5). La valeur par défaut de python-docx est Letter.
- Police du texte courant réglée une fois sur le style Normal (par exemple Calibri 11), jamais run par run.
- Titres avec les vrais styles : `doc.add_heading(texte, level=1)` pour 1, 2 et 3. Jamais un paragraphe en gras qui imite un titre, sinon le sommaire et la navigation ne marchent pas.
- Listes avec les styles `List Bullet` et `List Number`. Jamais de puce tapée à la main ("•", "-", "1.").
- Tableaux : `doc.add_table(rows, cols)` avec le style `Table Grid`, première ligne en gras, largeurs de colonnes fixées, texte aligné à gauche et nombres à droite.
- Espacement : règle `paragraph_format.space_after` sur le style. Jamais de paragraphes vides pour espacer. Saut de page avec `doc.add_page_break()` seulement quand il est voulu.
- Images : `doc.add_picture(chemin, width=Cm(14))` au maximum, jamais plus large que la zone de texte.
- Numéros de page : ajoute un champ PAGE dans le pied de page (élément XML `w:fldSimple` avec `w:instr="PAGE"`), centré.
- Langue : écris le document dans la langue de l'utilisateur, avec la typographie de cette langue.

## 3. Modifier un document existant

1. Copie le fichier joint dans le bac à sable avec l'action importer_fichier (url_fichier : le lien réel indiqué après le fichier, jamais inventé).
2. Ouvre-le avec `Document(chemin)` et modifie seulement ce qui est demandé : les styles, en-têtes et pieds de page existants restent.
3. Enregistre sous un nouveau nom. L'original reste intact.

## 4. Vérifier avant de livrer

Tu ne peux pas voir le rendu dans ce bac à sable : vérifie par le contenu. Rouvre le fichier produit et affiche la liste des titres avec leur niveau, le nombre de tableaux et d'images, et signale tout paragraphe vide ou titre sans texte. Relis le texte pour les fautes. Dis honnêtement à l'utilisateur que tu n'as pas pu contrôler la mise en page à l'œil si c'est le cas.

## 5. Livrer

Utilise l'action download_files avec path vers ce seul fichier : il reçoit son propre lien. Si le fichier dépasse la limite de taille de téléchargement, dis-le au lieu de livrer un fichier coupé. Termine par une phrase : ce que contient le document et ce que tu as choisi (format, polices).
