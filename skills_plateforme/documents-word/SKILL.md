---
name: "Word Documents"
description: "Official Classinus method for creating or editing a polished Word document (.docx): headings, lists, tables, pagination, and A4 layout. Read before producing a .docx file."
---

# Word documents (.docx)

Use this skill when the user wants a Word document created or modified. If they only need text to read in chat, do not create a file.

[English version] · [Français](SKILL.fr.md)

## 1. Prepare the sandbox

Use the `gerer_execution_code` tool.

1. Check the library: `python -c "import docx; print(docx.__version__ if hasattr(docx, '__version__') else 'ok')"`.
2. If it is missing, install it: `pip install python-docx`. If installation fails because there is no network, call the network action, then use `demander_acces_reseau` for `pypi.org` if needed. If pip refuses because the environment is managed, create a virtual environment: `python -m venv /home/user/venv`, then `/home/user/venv/bin/pip install python-docx`.
3. If nothing works, explain that and offer the simple `generer_document_word` tool (headings and paragraphs only).

Limits: each command may run for at most 60 seconds; `run_command` accepts up to 10,000 characters; a file or script must not exceed 1 MB. For a long document, write the content to a data file (for example, `contenu.json` using `write_file`) and keep the script that reads it short.

## 2. Build the document

- Use A4 pages with 2.5 cm margins: `section.page_width = Mm(210)`, `section.page_height = Mm(297)`, and margins set with `Cm(2.5)`. python-docx defaults to Letter.
- Set the body font once through the Normal style (for example, Calibri 11), never run by run.
- Use real heading styles: `doc.add_heading(text, level=1)` for levels 1, 2, and 3. Never imitate a heading with a bold paragraph, or the table of contents and navigation will not work.
- Use the `List Bullet` and `List Number` styles for lists. Never type bullet symbols or numbering manually (`•`, `-`, `1.`).
- Tables: use `doc.add_table(rows, cols)` with the `Table Grid` style, a bold first row, fixed column widths, left-aligned text, and right-aligned numbers.
- Spacing: set `paragraph_format.space_after` on the style. Never use empty paragraphs for spacing. Insert a page break only when intended with `doc.add_page_break()`.
- Images: use `doc.add_picture(path, width=Cm(14))` at most, never wider than the text area.
- Page numbers: add a PAGE field in the footer (XML element `w:fldSimple` with `w:instr="PAGE"`), centered.
- Language: write the document in the user's language, using that language's typography.

## 3. Modify an existing document

1. Copy the attached file into the sandbox with `importer_fichier` (use the real `url_fichier` link shown after the attachment; never invent one).
2. Open it with `Document(path)` and change only what was requested. Preserve existing styles, headers, and footers.
3. Save under a new name. Leave the original unchanged.

## 4. Verify before delivery

You cannot inspect the visual layout in this sandbox, so verify the content instead. Reopen the generated file and list all headings with their levels, the number of tables and images, and any empty paragraphs or headings without text.

Proofread the text. Be transparent if you could not visually inspect the page layout.

## 5. Deliver

Use the `download_files` action with the path to this file only. The file receives its own link. If it exceeds the download size limit, say so instead of providing a truncated file.

Finish with one sentence describing the document content and your choices (format and fonts).
