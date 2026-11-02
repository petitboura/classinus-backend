---
name: "Documents Excel"
description: "Méthode officielle Classinus pour créer ou modifier un classeur Excel (.xlsx) : plusieurs feuilles, formules vivantes, formats de nombres et de dates, mise en forme, graphiques. À lire avant de produire un fichier .xlsx."
---

# Classeurs Excel (.xlsx)

À utiliser quand l'utilisateur veut un classeur Excel, à créer ou à modifier. Pour un petit tableau à lire dans le chat, ne fabrique pas de fichier.

## 1. Préparer le bac à sable

Travaille avec l'outil gerer_execution_code.

1. Vérifie la bibliothèque : `python -c "import openpyxl; print(openpyxl.__version__)"`.
2. Si elle manque : `pip install openpyxl`. Si l'installation échoue faute de réseau, appelle l'action network, puis demander_acces_reseau pour pypi.org si besoin. Si pip refuse à cause d'un environnement géré, crée un environnement virtuel : `python -m venv /home/user/venv` puis `/home/user/venv/bin/pip install openpyxl`.
3. Si rien ne marche, dis-le et propose l'outil simple generer_document_excel (une seule feuille, sans formules).

Limites : une commande dure 60 secondes au plus, run_command accepte 10000 caractères, un fichier ou un script ne dépasse pas 1 Mo. Pour beaucoup de lignes, écris les données dans un fichier (write_file) et garde un script court qui les lit.

## 2. Construire le classeur

- Une feuille par sujet, avec un nom clair de 31 caractères au plus, sans les caractères interdits `\ / ? * [ ] :`, tous différents.
- Les chiffres sont de vrais nombres et les dates de vraies dates, jamais du texte. Un calcul se fait avec une formule : écris la formule dans la cellule, par exemple `ws["D10"] = "=SUM(D2:D9)"`, au lieu d'y mettre le résultat calculé en Python. Ainsi le classeur reste vivant quand l'utilisateur change une valeur.
- Les formules sont écrites en anglais (SUM, IF, VLOOKUP, SUMIF) avec la virgule comme séparateur, quelle que soit la langue de l'utilisateur. Excel les traduit à l'ouverture.
- Formats : `cell.number_format = "#,##0.00"` pour les montants, `"0.0%"` pour les pourcentages, `"DD/MM/YYYY"` pour les dates.
- En-têtes en gras avec un fond de couleur, ligne figée (`ws.freeze_panes = "A2"`), filtres (`ws.auto_filter.ref = ws.dimensions`), largeur de colonne adaptée au contenu le plus long (avec un minimum et un maximum).
- Les valeurs de départ (taux, hypothèses) vont dans des cellules dédiées, étiquetées, et les formules y renvoient. Jamais un nombre magique répété dans dix formules.
- Graphiques avec `openpyxl.chart` (BarChart, LineChart, PieChart) et `Reference` sur les cellules, avec un titre et des titres d'axes.
- Mise en forme conditionnelle et listes déroulantes (`DataValidation`) seulement quand elles servent.
- Très gros volume (plusieurs dizaines de milliers de lignes) : `Workbook(write_only=True)`.

## 3. Modifier un classeur existant

1. Copie le fichier joint dans le bac à sable avec importer_fichier (url_fichier : le lien réel indiqué après le fichier, jamais inventé).
2. Ouvre-le avec `load_workbook(chemin)` pour le modifier. Pour seulement lire les valeurs calculées, utilise `load_workbook(chemin, data_only=True)` et n'enregistre JAMAIS ce classeur : il aurait perdu toutes ses formules.
3. Enregistre sous un nouveau nom. L'original reste intact.

## 4. Vérifier avant de livrer

openpyxl n'évalue pas les formules et il n'y a pas de tableur dans ce bac à sable : tu ne peux pas voir les résultats. Vérifie donc par la structure : rouvre le fichier, liste les feuilles, les dimensions, et contrôle que chaque formule pointe vers des plages qui existent et qui sont bien remplies. Évite les erreurs classiques : division par zéro non protégée (`=IF(B2=0,0,A2/B2)`), plage décalée, référence à une feuille renommée. Dis honnêtement à l'utilisateur que les valeurs se calculent à l'ouverture dans Excel.

## 5. Livrer

Utilise l'action download_files avec path vers ce seul fichier. Si le fichier dépasse la limite de taille de téléchargement, dis-le. Termine par une phrase : les feuilles, ce que contient chacune et les hypothèses que tu as posées.
