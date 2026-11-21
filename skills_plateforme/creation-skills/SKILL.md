---
name: "Creating Skills"
description: "Official Classinus method for helping a user create or improve one of their own skills: define what it does and when it applies, write SKILL.md and extra files, then test it. Read when the user asks to create, write or improve a skill."
---

# Creating skills

Use this skill when the user wants to create, write, improve, import or export one of their own skills.

[English version] · [Français](SKILL.fr.md)

## 1. How a skill works

A skill is a folder with a required `SKILL.md` and optional text files (`scripts/`, `references/`, `assets/`). Only text files are supported. The prompt shows only the name and the description of each skill (the description is cut at 400 characters). When a request matches a description, the full `SKILL.md` is read, then other files only if the `SKILL.md` asks for them. So the description decides when the skill is used, and the body decides how well it is used.

Official Classinus skills are read-only. If a user skill and an official skill cover the same domain, the user skill wins.

## 2. Tool rules

Use `gerer_skill`. Never write, change or delete without a clear, explicit request from the user. If the request is vague, ask what they want first. Deleting asks for confirmation. Never show internal identifiers.

Actions: `lister`, `consulter`, `creer`, `modifier_infos`, `ecrire_fichier`, `remplacer_texte`, `supprimer_fichier`, `importer_zip`, `exporter_zip`, `supprimer`. The header (name and description) of `SKILL.md` is added and kept in sync automatically: `creer` takes only the body in `contenu`, and `modifier_infos` is the only way to change the name or the description.

## 3. Method

1. **Understand.** Ask what the skill does, when it should apply, what the user provides, what the result must look like, and for two or three real examples. Ask what goes wrong today without it. Then call `lister` to check that a similar skill does not already exist, official ones included.
2. **Write the description first.** Say what the skill does and when to use it, with the words the user would really say, including file types or keywords. Too broad and it triggers on everything, too narrow and it never triggers. Example. Weak: "Helps with reports." Better: "Writes the monthly sales report from a spreadsheet, in the company format. Use when the user mentions the monthly report, sales figures or the board summary."
3. **Write the body.** Short and in the imperative: steps in order, decisions, expected output, what never to do. Explain the reason behind a rule, because an explained rule is applied better than a bare one. Move long details to `references/` and say exactly when to read them. Put in `scripts/` only text that is deterministic.
4. **Create.** `creer` with the name, description and body, then `ecrire_fichier` for each extra file. Say in one sentence what was done.
5. **Test.** There is no automatic test runner here, so test by hand. Take three realistic requests: a typical one, an awkward one, and one that must not trigger the skill. Check that the description matches the first two and not the third, and that the body gives enough to do the task without guessing. Suggest that the user tries a real request in a new message and tells you the result.
6. **Improve.** `remplacer_texte` for a small fix, `ecrire_fichier` to rewrite a file, `modifier_infos` for the name or description. Re-read the file with `consulter` after a change.

## 4. Import and export

- `exporter_zip` produces a downloadable zip, one folder per skill, so the skills can be backed up or moved. Leave `skill_id` empty to export all of them.
- `importer_zip` adds all the skills of a zip attached to the chat at once. Do not read and recreate them one by one.

## 5. Pitfalls

- A skill is saved as text and can be exported or shared. Never put passwords, keys or personal data in it.
- Do not copy a whole manual into `SKILL.md`. Keep what the model would not know or would get wrong.
- Do not create a skill for a one-off request. A skill is for something the user will do again.
