---
name: "Excel Documents"
description: "Official Classinus method for creating or editing an Excel workbook (.xlsx): multiple sheets, live formulas, number and date formats, formatting, and charts. Read before producing an .xlsx file."
---

# Excel workbooks (.xlsx)

Use this skill when the user wants an Excel workbook created or modified. For a small table that can be read directly in chat, do not create a file.

[English version] · [Français](SKILL.fr.md)

## 1. Prepare the sandbox

Use the `gerer_execution_code` tool.

1. Check the library: `python -c "import openpyxl; print(openpyxl.__version__)"`.
2. If it is missing: `pip install openpyxl`. If installation fails because there is no network, call the network action, then use `demander_acces_reseau` for `pypi.org` if needed. If pip refuses because the environment is managed, create a virtual environment: `python -m venv /home/user/venv`, then `/home/user/venv/bin/pip install openpyxl`.
3. If nothing works, explain that and offer the simple `generer_document_excel` tool (one sheet, no formulas).

Limits: each command may run for at most 60 seconds; `run_command` accepts up to 10,000 characters; a file or script must not exceed 1 MB. For large datasets, write the data to a file with `write_file` and keep the script that reads it short.

## 2. Build the workbook

- Use one sheet per topic. Sheet names must be distinct, clear, at most 31 characters, and must not contain the forbidden characters `\ / ? * [ ] :`.
- Store numbers as actual numbers and dates as actual dates, never as text. Use formulas for calculations. For example, write `ws["D10"] = "=SUM(D2:D9)"` rather than calculating the result in Python. This keeps the workbook live when the user changes a value.
- Write formulas in English (`SUM`, `IF`, `VLOOKUP`, `SUMIF`) with commas as separators, regardless of the user's language. Excel translates them when the workbook opens.
- Formats: `cell.number_format = "#,##0.00"` for amounts, `"0.0%"` for percentages, and `"DD/MM/YYYY"` for dates.
- Use bold headers with a background color, freeze the header row (`ws.freeze_panes = "A2"`), enable filters (`ws.auto_filter.ref = ws.dimensions`), and size columns for their longest content within sensible minimum and maximum widths.
- Put starting values (rates, assumptions) in dedicated, labelled cells and refer to those cells in formulas. Never repeat a magic number across ten formulas.
- Create charts with `openpyxl.chart` (`BarChart`, `LineChart`, `PieChart`) and `Reference` objects pointing to worksheet cells. Include a chart title and axis titles.
- Use conditional formatting and dropdown lists (`DataValidation`) only when they are useful.
- For very large datasets (tens of thousands of rows), use `Workbook(write_only=True)`.

## 3. Modify an existing workbook

1. Copy the attached file into the sandbox with `importer_fichier` (use the real `url_fichier` link shown after the attachment; never invent one).
2. Open it with `load_workbook(path)` to modify it. If you only need to read calculated values, use `load_workbook(path, data_only=True)` and NEVER save that workbook: doing so would remove its formulas.
3. Save under a new name. Leave the original unchanged.

## 4. Verify before delivery

openpyxl does not calculate formulas, and there is no spreadsheet application in this sandbox, so you cannot see the calculated results here.

Verify the workbook structurally: reopen it, list the sheets and their dimensions, and check that each formula refers to existing, populated ranges. Avoid common errors such as unguarded division by zero (`=IF(B2=0,0,A2/B2)`), shifted ranges, or references to renamed sheets.

Be transparent with the user: values will be calculated when the file is opened in Excel.

## 5. Deliver

Use the `download_files` action with the path to this file only. If the file exceeds the download size limit, say so.

Finish with one sentence describing the sheets, what each contains, and the assumptions you made.
