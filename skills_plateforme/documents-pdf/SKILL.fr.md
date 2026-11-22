> [English version](./SKILL.md) · **Version française**

---
name: "Documents PDF"
description: "Méthode officielle Classinus pour créer un PDF ou modifier un PDF existant : fusionner, découper, pivoter, filigrane, remplir un formulaire, protéger, extraire des tableaux. À lire avant de produire ou modifier un PDF. Pour seulement lire un PDF, utiliser Lecture de PDF."
---

# Fichiers PDF

À utiliser quand l'utilisateur veut un PDF créé, ou un PDF existant modifié. S'il veut seulement lire ou comprendre un PDF, utilise le skill Lecture de PDF. S'il a seulement besoin d'un texte à lire dans le chat, ne fabrique pas de fichier.

## 1. Choisir le bon chemin

1. Un document neuf et simple (titre, intertitres, listes, tableaux, blocs de code) sans mise en page particulière : utilise l'outil `generer_document` avec un titre et un contenu en Markdown. Il renvoie le lien public du PDF, et le fichier est aussi rangé dans la bibliothèque de l'utilisateur. C'est le chemin le plus rapide.
2. Fusionner, couper, tourner des pages ou remplir un formulaire standard sur des PDF joints par l'utilisateur : utilise les outils dédiés, sans bac à sable. `fusionner_pdf` (2 à 20 PDF, dans l'ordre donné), `decouper_pdf` (plages de pages comme `["1-3", "4-6"]`, ou toutes les N pages), `tourner_pages_pdf` (90, 180 ou 270 degrés, toutes les pages ou certaines), `remplir_formulaire_pdf` (appelle-le d'abord sans valeurs pour lister les champs, puis une seconde fois avec les valeurs données par l'utilisateur). Chacun renvoie un nouveau fichier et laisse l'original intact. Un PDF protégé par mot de passe ne peut pas être ouvert par ces outils.
3. Tout le reste (filigrane, protection par mot de passe, reconnaissance de texte, mise en page précise, écritures non latines, formulaire que l'outil ne sait pas remplir) : utilise le bac à sable de code, à partir de la section 2.

## 2. Préparer le bac à sable

Utilise l'outil `gerer_execution_code`. S'il n'est pas disponible, demande la catégorie `execution_code` avec `demander_outils`.

1. Vérifie les bibliothèques en une commande : `python -c "import pypdf, reportlab, pdfplumber; print('ok')"`.
2. S'il en manque : `pip install pypdf reportlab pdfplumber`. Si l'installation échoue faute de réseau, utilise l'action `network`, puis `demander_acces_reseau` pour `pypi.org`. Si pip refuse parce que l'environnement est géré, crée un environnement virtuel : `python -m venv /home/user/venv`, puis utilise `/home/user/venv/bin/pip`.
3. Vérifie les programmes facultatifs : `which qpdf pdftotext pdftoppm tesseract ocrmypdf`. Ne suppose jamais qu'un d'eux est installé. N'utilise que ce que tu as trouvé, et ne prétends jamais avoir une fonction (OCR, rendu des pages) que tu n'as pas pu lancer.
4. Limites par défaut : une commande s'arrête au bout de 60 secondes (utilise `run_background` puis `command_status` pour un travail plus long), `run_command` accepte 10 000 caractères, un fichier ou un script ne doit pas dépasser 1 Mo. Pour un contenu long, écris-le dans un fichier de données avec `write_file` et garde court le script qui le lit.
5. Si rien ne marche, explique pourquoi et propose `generer_document` à la place.

## 3. Travailler sur une copie

Copie le fichier joint dans le bac à sable avec `importer_fichier`, en utilisant le vrai lien `url_fichier` affiché après la pièce jointe (n'en invente jamais un). N'écrase jamais l'original : enregistre le résultat sous un nouveau nom.

## 4. Opérations courantes

- **Nouveau PDF soigné** : reportlab Platypus (`SimpleDocTemplate`, `Paragraph`, `Table`) avec `pagesize=A4` et des marges de 2 cm. Les polices intégrées couvrent les accents d'Europe de l'Ouest mais pas les autres écritures (arabe, ou lettres du bambara comme ɛ ɔ ɲ ŋ). Pour celles-ci, cherche une police TTF sur le système (`fc-list`) et enregistre-la avec `pdfmetrics.registerFont`. S'il n'y en a aucune, dis-le à l'utilisateur.
- **Fusionner** : `PdfWriter`, puis `append` de chaque fichier dans l'ordre donné par l'utilisateur.
- **Découper ou extraire des pages** : un fichier de sortie par plage de pages demandée.
- **Pivoter** : `page.rotate(90)` sur les seules pages concernées.
- **Filigrane** : fabrique un PDF d'une page avec reportlab, puis `page.merge_page(...)` sur chaque page.
- **Remplir un formulaire** : liste d'abord les champs avec `reader.get_fields()` et montre-les à l'utilisateur. Ne remplis que les champs pour lesquels il a donné une valeur, puis appelle `writer.set_need_appearances_writer(True)` pour que les valeurs s'affichent.
- **Extraire du texte ou des tableaux** : `pdfplumber` (`extract_text`, `extract_tables`). Les tableaux d'un scan ne marchent pas sans OCR.
- **Protéger par mot de passe** : `writer.encrypt(...)`. Demande le mot de passe à l'utilisateur. N'en invente jamais un.
- **PDF scanné (sans couche de texte)** : OCR seulement si `tesseract` ou `ocrmypdf` a été trouvé. Si l'utilisateur veut seulement le lire, `lire_document_conversation` peut lire les pages scannées par reconnaissance de texte quand tu le demandes.

## 5. Vérifier avant de livrer

Rouvre le fichier produit avec pypdf : nombre de pages, taille des pages, texte de la première page, et champs remplis pour un formulaire. Pour une fusion, vérifie que le nombre total de pages est égal à la somme des fichiers d'entrée. Tu ne peux pas voir les pages rendues sauf si tu les as vraiment rendues, dis-le quand ce n'est pas le cas.

## 6. Livrer

Utilise l'action `download_files` avec le chemin de ce seul fichier. S'il dépasse la limite de téléchargement, dis-le au lieu de fournir un fichier tronqué.

Termine par une phrase décrivant le résultat (pages, ce qui a changé) et tes choix.
