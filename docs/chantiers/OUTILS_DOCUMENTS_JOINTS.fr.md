# Travail sur les documents joints (modifier un fichier, travailler sur des PDF)

[English version](OUTILS_DOCUMENTS_JOINTS.md) · **Version française**

Ajouté le 21 novembre 2026 à la demande de Bourama. Quand un utilisateur joint un document au chat, Classinus peut maintenant le modifier et rendre un nouveau fichier, au lieu de seulement le lire ou d'en créer un tout neuf. L'original n'est jamais modifié : chaque outil produit un NOUVEAU fichier, rangé dans la bibliothèque de l'utilisateur avec l'origine « Généré par l'IA ».

## Les outils

Cinq outils sur le serveur MCP `generation` (chat seulement). Ils ne sont PAS sur le serveur MCP public (`core/serveur_mcp_espace.py`) : les y ajouter demande l'accord explicite de Bourama.

| Outil | Ce qu'il fait |
| --- | --- |
| `modifier_document_conversation` | Modifie un fichier Word (.docx), Excel (.xlsx) ou PowerPoint (.pptx) joint, avec une liste d'opérations. |
| `fusionner_pdf` | Fusionne de 2 à 20 PDF joints, dans l'ordre donné. |
| `decouper_pdf` | Coupe un PDF par plages de pages (`["1-3", "4-6"]`) ou toutes les N pages. 20 fichiers au plus par appel. |
| `tourner_pages_pdf` | Tourne une partie ou toutes les pages de 90, 180 ou 270 degrés. |
| `remplir_formulaire_pdf` | Deux temps : appelé sans valeurs, il liste les champs du formulaire (aucun fichier créé) ; appelé avec des valeurs, il les remplit. |

Lire les tableaux d'un PDF n'est pas un nouvel outil : c'est un nouveau mode, `tableaux`, de l'outil existant `lire_document_conversation`. Il rend des tableaux Markdown, seulement pour les pages à texte natif (un scan n'a pas de tableau reconnaissable).

Les numéros de page, de diapositive, de ligne et de feuille commencent à 1, comme à l'écran.

## Opérations de `modifier_document_conversation`

Le modèle envoie une liste ; elles s'appliquent dans l'ordre sur une copie en mémoire. Si une seule échoue, **rien n'est livré** et le message nomme l'opération en cause : un fichier n'est jamais modifié à moitié.

- **Word** : `remplacer_texte` (corps, tableaux, en-têtes et pieds de page ; mise en forme gardée, même quand Word a coupé le texte en plusieurs morceaux), `ajouter_paragraphe`, `ajouter_titre`, `supprimer_paragraphe`, `ajouter_tableau`.
- **Excel** : `definir_cellule` (une valeur qui commence par `=` reste une formule), `ajouter_ligne`, `ajouter_colonne`, `supprimer_ligne`, `ajouter_feuille`, `renommer_feuille`. Les formules existantes sont gardées.
- **PowerPoint** : `remplacer_texte`, `ajouter_diapositive` (avec une position facultative, dans les mises en page du fichier lui-même), `supprimer_diapositive`, `modifier_notes`.

## Quand utiliser l'outil, quand utiliser le bac à sable

Les skills de plateforme Word, Excel et PowerPoint (`skills_plateforme/documents-*`) avaient déjà une méthode pour modifier un fichier : le copier dans le bac à sable de code et le changer avec une bibliothèque. Les deux restent, et la section 3 de chaque skill dit maintenant laquelle choisir :

- **Changement simple** (remplacer un texte, ajouter une ligne, supprimer une diapositive) : l'outil. Pas de bac à sable, pas de réseau, plus rapide.
- **Contrôle fin** (styles, mise en page, formats de nombre, graphiques, images) : la méthode du bac à sable du skill.

Le skill PDF (`documents-pdf`) suit le même partage : les quatre outils PDF pour fusionner, couper, tourner et remplir un formulaire standard sur des PDF joints, et le bac à sable pour tout le reste (filigrane, mot de passe, reconnaissance de texte, mise en page précise). Les skills de lecture (`lecture-pdf`, `lecture-fichiers`) renvoient vers le nouveau mode `tableaux`.

## Limites

- Seulement les fichiers joints au chat par l'utilisateur (même règle que `lire_document_conversation` : périmètre strict sur le compte et sur les fichiers du chat). Un fichier généré plus tôt par l'IA ne se modifie pas avec ces outils.
- Les anciens formats Office (.doc, .xls, .ppt) ne se modifient pas. Un PDF protégé par mot de passe ne s'ouvre pas.
- Seuls les formulaires PDF standard (AcroForm) sont remplis, pas les formulaires XFA ni les documents à plat.
- Taille maximale d'un fichier : 25 Mo, modifiable par la variable d'environnement `DOCUMENT_TRAVAIL_TAILLE_MAX_MO` (`core/limites_media.py`).
- Excel : les images et graphiques sont gardés dans la mesure où `openpyxl` les gère ; les macros (.xlsm) ne sont pas prises en charge.

## Code

| Fichier | Rôle |
| --- | --- |
| `core/modification_fichiers_office.py` | Les opérations Word, Excel et PowerPoint : des octets en entrée, des octets en sortie. |
| `core/travail_pdf.py` | Fusion, découpage, rotation, champs de formulaire et tableaux, avec PyMuPDF (déjà une dépendance). |
| `core/outils_travail_documents.py` | Les cinq outils MCP : retrouver le fichier joint, publier le résultat, l'enregistrer dans la bibliothèque. |
| `core/lecture_document_conversation.py` | Le nouveau mode de lecture `tableaux`. |
| `migrations/2026_11_21_outils_travail_documents.sql` | Déclare les cinq outils comme disponibles côté plateforme. |
| `test_travail_documents.py`, `test_outils_travail_documents.py` | Tests avec de vrais fichiers Word, Excel, PowerPoint et PDF. |

Branchement : libellé et icône dans `core/registre_outils.py` (`REGISTRE_AFFICHAGE_OUTILS`), libellés anglais dans `core/libelles_outils_anglais.py`, catégories `generation_documents` et `document_joint`, et `core/main.py` donne les outils au modèle dès qu'un document est joint.

## Mise en ligne

1. Déployer le code du backend.
2. Appliquer la migration, d'abord sur la base de staging, puis en production. Sans elle, les outils existent dans le code mais ne sont jamais proposés au modèle (la liste est gardée 24 heures en cache : redéployer ou recharger le catalogue d'outils).
3. Lancer la synchronisation des skills de plateforme (`python -m scripts.synchroniser_skills_plateforme simuler`, puis `appliquer`) pour que les skills mis à jour arrivent en base.

Aucune table ni colonne contenant des données d'utilisateur n'est ajoutée : rien ne change pour la suppression de compte ni pour l'export des données, les fichiers générés passant par la bibliothèque existante, déjà couverte.
