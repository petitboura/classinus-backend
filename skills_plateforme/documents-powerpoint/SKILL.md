---
name: "PowerPoint Presentations"
description: "Official Classinus method for creating or editing a readable PowerPoint presentation (.pptx): 16:9 format, one idea per slide, native charts, and speaker notes. Read before producing a .pptx file."
---

# PowerPoint presentations (.pptx)

Use this skill when the user wants a PowerPoint file created or modified. If they only need a presentation outline to read in chat, do not create a file.

[English version] · [Français](SKILL.fr.md)

## 1. Prepare the sandbox

Use the `gerer_execution_code` tool.

1. Check the library: `python -c "import pptx; print(pptx.__version__)"`.
2. If it is missing: `pip install python-pptx`. If installation fails because there is no network, call the network action, then use `demander_acces_reseau` for `pypi.org` if needed. If pip refuses because the environment is managed, create a virtual environment: `python -m venv /home/user/venv`, then `/home/user/venv/bin/pip install python-pptx`.
3. If nothing works, explain that and offer the simple `generer_document_powerpoint` tool (titles and text only).

Limits: each command may run for at most 60 seconds; `run_command` accepts up to 10,000 characters; a file or script must not exceed 1 MB. Embedded images count toward this limit: reduce them with Pillow (maximum width 1600 px, JPEG) before inserting them.

## 2. Build the presentation

- Use 16:9 format: `prs.slide_width = Inches(13.333)` and `prs.slide_height = Inches(7.5)`. python-pptx defaults to 4:3.
- Use the blank layout (`prs.slide_layouts[6]`) and place text areas and shapes manually. Default template layouts are designed for 4:3 and will be misaligned in 16:9.
- One idea per slide. The title should state the conclusion (eight words maximum), not just the topic. Keep body text to about 30 words maximum. Use three to five short bullets or one visual.
- Font sizes: title 32–40 pt, body 18–24 pt, never below 14 pt. If text does not fit, split the slide in two instead of shrinking the font.
- Use one palette: one dominant color, one accent color, and high-contrast text. Use one font family. Keep the same margins (0.6 inch) and title positions on every slide.
- Include an opening slide (title and subtitle), one slide per idea, and a conclusion with next steps. Do not add an empty "Thank you" slide.
- Use native charts: `CategoryChartData` and `slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, ...)`, with readable titles and legends. A native chart remains editable by the user, unlike an image.
- Use images only when provided by the user or when they support the content. Never use decorative images. Preserve their aspect ratio.
- Add speaker notes when useful: `slide.notes_slide.notes_text_frame.text = "..."`.

## 3. Modify an existing presentation

1. Copy the attached file into the sandbox with `importer_fichier` (use the real `url_fichier` link shown after the attachment; never invent one).
2. Open it with `Presentation(path)`, preserve its layouts and theme, and change only what was requested.
3. Save under a new name. Leave the original unchanged.

## 4. Verify before delivery

You cannot inspect the visual rendering in this sandbox, so verify dimensions instead. Reopen the output and, for every slide, check that each shape remains inside the slide bounds (`left + width <= slide_width`, `top + height <= slide_height)). Count words and flag slides that exceed 40 words or contain an overflowing shape.

Proofread the text. Be transparent if you could not visually inspect the rendered slides.

## 5. Deliver

Use the `download_files` action with the path to this file only. If the file exceeds the download size limit, say so.

Finish with one sentence stating the number of slides, presentation storyline, and design choices.
