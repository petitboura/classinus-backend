# Working on attached documents (edit a file, work on PDFs)

**English version** · [Version française](OUTILS_DOCUMENTS_JOINTS.fr.md)

Added on 21 November 2026 at Bourama's request. When a user attaches a document to the chat, Classinus can now change it and hand back a new file, instead of only reading it or creating a brand new one. The original is never modified: every tool produces a NEW file, saved in the user's library under the origin "AI generated".

## The tools

Five tools on the `generation` MCP server (chat only). They are NOT on the public MCP server (`core/serveur_mcp_espace.py`): adding them there needs Bourama's explicit approval.

| Tool | What it does |
| --- | --- |
| `modifier_document_conversation` | Edits an attached Word (.docx), Excel (.xlsx) or PowerPoint (.pptx) file with a list of operations. |
| `fusionner_pdf` | Merges 2 to 20 attached PDFs, in the order given. |
| `decouper_pdf` | Splits a PDF by page ranges (`["1-3", "4-6"]`) or every N pages. 20 files at most per call. |
| `tourner_pages_pdf` | Rotates some or all pages by 90, 180 or 270 degrees. |
| `remplir_formulaire_pdf` | Two steps: called without values it lists the form fields (no file created); called with values it fills them. |

Reading tables from a PDF is not a new tool: it is a new mode, `tableaux`, of the existing `lire_document_conversation`. It returns Markdown tables, only for pages that have native text (a scan has no recognisable table).

Page, slide, row and sheet numbers start at 1, as on screen.

## Operations of `modifier_document_conversation`

The model sends a list; they run in order on a copy in memory. If one fails, **nothing is delivered** and the message names the failing operation, so a file is never half edited.

- **Word**: `remplacer_texte` (body, tables, headers and footers; formatting kept, even when Word split the text across several runs), `ajouter_paragraphe`, `ajouter_titre`, `supprimer_paragraphe`, `ajouter_tableau`.
- **Excel**: `definir_cellule` (a value starting with `=` stays a formula), `ajouter_ligne`, `ajouter_colonne`, `supprimer_ligne`, `ajouter_feuille`, `renommer_feuille`. Existing formulas are kept.
- **PowerPoint**: `remplacer_texte`, `ajouter_diapositive` (with an optional position, using the file's own layouts), `supprimer_diapositive`, `modifier_notes`.

## When to use the tool, when to use the sandbox

The Word, Excel and PowerPoint platform skills (`skills_plateforme/documents-*`) already had a method to modify a file: copy it into the code sandbox and edit it with a library. Both stay, and section 3 of each skill now says which to choose:

- **Simple change** (replace a text, add a row, delete a slide): the tool. No sandbox, no network, faster.
- **Fine control** (styles, layout, number formats, charts, images): the sandbox method of the skill.

There is no skill for PDFs: the four PDF tools are the only built in way to merge, split, rotate and fill them.

## Limits

- Only files attached to the chat by the user (same rule as `lire_document_conversation`: strict scope on the account and on chat files). A file the AI generated earlier cannot be edited with these tools.
- Old Office formats (.doc, .xls, .ppt) cannot be edited. A password protected PDF cannot be opened.
- Only standard PDF forms (AcroForm) are filled, not XFA forms or flat documents.
- Maximum file size: 25 MB, changed with the environment variable `DOCUMENT_TRAVAIL_TAILLE_MAX_MO` (`core/limites_media.py`).
- Excel: images and charts are kept as far as `openpyxl` supports them; macros (.xlsm) are not supported.

## Code

| File | Role |
| --- | --- |
| `core/modification_fichiers_office.py` | The Word, Excel and PowerPoint operations: bytes in, bytes out. |
| `core/travail_pdf.py` | Merge, split, rotate, form fields and tables, with PyMuPDF (already a dependency). |
| `core/outils_travail_documents.py` | The five MCP tools: find the attached file, publish the result, save it to the library. |
| `core/lecture_document_conversation.py` | The new `tableaux` reading mode. |
| `migrations/2026_11_21_outils_travail_documents.sql` | Declares the five tools as available on the platform. |
| `test_travail_documents.py`, `test_outils_travail_documents.py` | Tests with real Word, Excel, PowerPoint and PDF files. |

Wiring: display label and icon in `core/registre_outils.py` (`REGISTRE_AFFICHAGE_OUTILS`), English labels in `core/libelles_outils_anglais.py`, categories `generation_documents` and `document_joint`, and `core/main.py` gives the tools to the model as soon as a document is attached.

## Putting it live

1. Deploy the backend code.
2. Apply the migration, on the staging database first, then production. Without it the tools exist in the code but are never offered to the model (the list is cached for 24 hours, so redeploy or reload the tool catalogue).
3. Run the platform skills synchronisation (`python -m scripts.synchroniser_skills_plateforme simuler`, then `appliquer`) so the updated skills reach the database.

No table or column holding user data is added, so nothing changes for account deletion or data export: generated files go through the existing library, already covered.
