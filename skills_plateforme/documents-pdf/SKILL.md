---
name: "PDF Documents"
description: "Official Classinus method for creating a PDF or changing an existing one: merge, split, rotate, watermark, fill a form, protect, extract tables. Read before producing or modifying a PDF. To only read a PDF, use PDF Reading."
---

# PDF files

Use this skill when the user wants a PDF created, or an existing PDF changed. If they only want to read or understand a PDF, use the PDF Reading skill. If they only need text to read in chat, do not create a file.

[English version] · [Français](SKILL.fr.md)

## 1. Choose the right path

1. A simple new document (title, headings, lists, tables, code blocks) with no special layout: use the `generer_document` tool with a title and Markdown content. It returns the public link of the PDF, and the file is also saved in the user's library. This is the fastest path.
2. Merge, split, rotate pages or fill a standard form on PDFs the user attached: use the dedicated tools, no sandbox needed. `fusionner_pdf` (2 to 20 PDFs, in the order given), `decouper_pdf` (page ranges such as `["1-3", "4-6"]`, or every N pages), `tourner_pages_pdf` (90, 180 or 270 degrees, all pages or some), `remplir_formulaire_pdf` (call it without values first to list the fields, then again with the values the user gave). Each returns a new file and leaves the original intact. A password protected PDF cannot be opened by these tools.
3. Anything else (watermark, password protection, OCR, precise layout, non-Latin scripts, a form the tool cannot fill): use the code sandbox, from section 2.

## 2. Prepare the sandbox

Use the `gerer_execution_code` tool. If it is not available, request the `execution_code` category with `demander_outils`.

1. Check the libraries in one command: `python -c "import pypdf, reportlab, pdfplumber; print('ok')"`.
2. If something is missing: `pip install pypdf reportlab pdfplumber`. If installation fails because there is no network, use the `network` action, then `demander_acces_reseau` for `pypi.org`. If pip refuses because the environment is managed, create a virtual environment: `python -m venv /home/user/venv`, then use `/home/user/venv/bin/pip`.
3. Check the optional programs: `which qpdf pdftotext pdftoppm tesseract ocrmypdf`. Never assume one is installed. Only use what you found, and never claim a feature (OCR, page rendering) that you could not run.
4. Limits, by default: a command stops after 60 seconds (use `run_background` then `command_status` for longer work), `run_command` accepts 10,000 characters, a file or script must not exceed 1 MB. For long content, write it to a data file with `write_file` and keep the script that reads it short.
5. If nothing works, explain why and offer `generer_document` instead.

## 3. Work from a copy

Copy the attached file into the sandbox with `importer_fichier`, using the real `url_fichier` link shown after the attachment (never invent one). Never overwrite the original: save the result under a new name.

## 4. Common operations

- **New designed PDF**: reportlab Platypus (`SimpleDocTemplate`, `Paragraph`, `Table`) with `pagesize=A4` and 2 cm margins. The built-in fonts cover Western European accents but not other scripts (Arabic, or Bambara letters such as ɛ ɔ ɲ ŋ). For those, look for a TTF font on the system (`fc-list`) and register it with `pdfmetrics.registerFont`. If none exists, tell the user.
- **Merge**: `PdfWriter`, then `append` each file in the order the user gave.
- **Split or extract pages**: one output file per page range requested.
- **Rotate**: `page.rotate(90)` on the pages concerned only.
- **Watermark**: build a one-page PDF with reportlab, then `page.merge_page(...)` on every page.
- **Fill a form**: list the fields first with `reader.get_fields()` and show them to the user. Fill only the fields for which they gave a value, then call `writer.set_need_appearances_writer(True)` so the values display.
- **Extract text or tables**: `pdfplumber` (`extract_text`, `extract_tables`). Tables from a scan will not work without OCR.
- **Protect with a password**: `writer.encrypt(...)`. Ask the user for the password. Never invent one.
- **Scanned PDF (no text layer)**: OCR only if `tesseract` or `ocrmypdf` was found. If the user only needs to read it, `lire_document_conversation` can read scanned pages by text recognition when asked.

## 5. Verify before delivery

Reopen the output with pypdf: page count, page size, text of the first page, and the filled fields for a form. For a merge, check that the total page count equals the sum of the inputs. You cannot see the rendered pages unless you really rendered them, so say so when you did not.

## 6. Deliver

Use the `download_files` action with the path to this file only. If it exceeds the download size limit, say so instead of providing a truncated file.

Finish with one sentence describing the result (pages, what changed) and your choices.
