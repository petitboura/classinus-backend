---
name: "Interface Design"
description: "Official Classinus method for designing a web page, site or app interface with a deliberate look instead of a generic template. Read before writing HTML, CSS or JavaScript for a page, site, dashboard or small tool."
---

# Interface design

Use this skill when the user wants a web page, landing page, site, dashboard, app screen or small tool built in HTML, CSS and JavaScript. Do not use it for a short code snippet that you only explain in chat.

[English version] · [Français](SKILL.fr.md)

## 1. Frame before coding

If something essential is missing (purpose, audience, language, available content), ask one short question. Otherwise state your assumptions in one line and build. Real content beats placeholders: use the user's own texts, names and figures, in their language. Never use lorem ipsum.

## 2. Choose a direction and commit to it

Pick one clear visual direction (editorial, calm, playful, technical, bold...) and apply it everywhere. A generic result is one where nothing was chosen: default purple gradients, identical rounded cards, a centered title over a vague tagline.

- **Color**: one dominant color, one accent, tinted neutrals instead of pure grey. Define them once as CSS custom properties.
- **Type**: at most two families (one for titles, one for text), a clear scale with strong contrast between levels, comfortable line length (around 60 to 75 characters) and line height. Always give a fallback font stack, because a font that fails to load must not break the layout.
- **Space**: one spacing scale (multiples of 4 or 8 px), generous margins, consistent alignment.
- **Detail**: one memorable element (a shape, a texture, an unusual layout) rather than ten decorations.

## 3. Quality checklist

- **Responsive**: design for a narrow phone first (about 360 px), then wide screens. Include `<meta name="viewport" content="width=device-width, initial-scale=1">`. No horizontal scrolling. Touch targets of at least 44 px.
- **Accessible**: semantic HTML (`header`, `main`, `nav`, real `button` elements), text contrast of at least 4.5:1, visible focus, alt text on images, labels on form fields, a `lang` attribute.
- **Motion**: short transitions (150 to 300 ms) when something opens, closes or changes. Nothing appears or disappears abruptly. Respect `prefers-reduced-motion`.
- **States**: design loading, empty and error states. A blank area is a bug.
- **Texts ready to translate**: if the page can be multilingual, keep every visible text in one object or dictionary, not scattered in the markup.
- **Dark mode**: when relevant, switch the CSS custom properties with `prefers-color-scheme`.
- **Images**: never invent image links. Use inline SVG, CSS shapes, or files the user provided.
- **Dependencies**: prefer plain HTML, CSS and JavaScript. If a library is truly needed, say which and why.

## 4. Deliver

Put the entry point in `index.html` at the root and use relative paths.

- Source code to download (one or several files): `generer_code` with `nom_projet` and `fichiers`, a dictionary `{path: content}`. One file is returned directly, several become a zip.
- Static site as a zip to host elsewhere: `generer_site_zip`, same parameters.
- Online link: `deployer_site`, same parameters, only if the tool is available. If it is not, say so and offer the zip.

You cannot see the rendered page unless you really opened it, so re-read your code for broken paths, unclosed tags and missing alt text, and say you did not view it.

Finish with one sentence on the design choices and offer one or two concrete adjustments.
