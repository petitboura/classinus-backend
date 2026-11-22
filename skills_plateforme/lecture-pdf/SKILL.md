---
name: "PDF Reading"
description: "Official Classinus method for reading a PDF the user attached or linked: check its size first, search long documents, read by pages, handle scans and tables. Read before answering a question about a PDF."
---

# Reading PDFs

Use this skill when the user asks a question about a PDF (attached or online), wants a summary, a quote, or data from it. To create or change a PDF, use the PDF Documents skill.

[English version] · [Français](SKILL.fr.md)

## 1. Look before reading

Attached files are not read automatically. The message only shows their name, type, size and number of pages, with the real link in brackets after "Lien réel du fichier". Never invent that link.

Start with `lire_document_conversation` in `infos` mode: type, size, number of pages. It costs nothing and tells you how to read the rest.

## 2. Pick the right mode

- **Short document (a few pages)**: `texte` mode.
- **Long document, question about a topic**: `recherche` mode with the word or expression. It returns the passages with their page. Then use `pages` mode with `debut_page` and `fin_page` around the best hits.
- **User names a page, a chapter or a section**: `pages` mode on that range.
- **User wants the data of a table (statement, report card, invoice)**: `tableaux` mode with `debut_page` and `fin_page`. It returns Markdown tables.
- **Summary of a whole long document**: read it in order, slice by slice. When a reply tells you to call the tool again with a new `debut_page` or `debut_caractere`, do it before concluding. If you stop early, say exactly which pages you read.

## 3. Scanned pages

A page without native text is read by text recognition, only when you ask for it, and the quality can vary. If the result is empty or garbled, say so, say which pages are affected, and do not guess the content.

## 4. Tables, figures and numbers

Plain text extraction flattens tables: use the `tableaux` mode to get them as tables. It only works on pages with native text, never on a scan; for a scanned page, read it with the `pages` mode and say that the table structure may be lost. Quote numbers exactly as written and give the page. To compute, convert or plot from a table, import the file into the sandbox (`gerer_execution_code`, action `importer_fichier`) and extract it with `pdfplumber`, after checking that it is installed.

## 5. PDF on the web

For a PDF given as a link (not attached), use `lire_document_externe` with the `url`, then `a_partir_du_caractere` to continue and `rechercher` to find a word. The same slice-by-slice logic applies.

## 6. Answering

- Give the page number with each fact you take from the document.
- Separate what the document says from your own comments.
- If the document is unreadable, protected or does not contain the answer, say it plainly. Never fill the gap from memory as if it came from the document.
- For other file types (video, audio, archive, spreadsheet), see the Attached Files skill.
