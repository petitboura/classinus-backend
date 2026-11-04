# DISABLED SECTION: NEVER REUSE THIS CODE

[English version] · [Français](LISEZ_MOI_NE_JAMAIS_REUTILISER.fr.md)

Bourama's decision from 29 August 2026: the **Programme** feature (class/subject/chapter structure, attached documents/exercises/exams, Programme plugins, audits, and library classification within a Programme) is **fully disabled and isolated**.

## What was done

- The nine files belonging exclusively to this feature were moved here unchanged:
  - `api/programmes.py`
  - `api/plugins_programme.py`
  - `api/contenu_programme.py`
  - `api/emplacements_bibliotheque_programme.py`
  - `api/audits_programme.py`
  - `core/programme_llm.py`
  - `core/programme_ecriture.py`
  - `core/audit_programme.py`
  - `core/bibliotheque_programme.py`
- All imports, FastAPI route registrations, MCP tools, chat system-prompt injections, and registry entries connecting these files to the rest of the application were removed from active code. See the related commits.
- Nothing was deleted from the database. These tables still exist but are no longer called by active code: `programmes`, `matieres`, `chapitres`, `documents_programme`, `exercices_programme`, `examens_programme`, `examen_chapitres`, `plugins_programme`, `plugin_telechargements`, `audits_programme`, `audits_matiere`, `audits_chapitre`, `historique_ecritures_programme`, `bibliotheque_emplacements_programme`, `classements_transversaux`, and `classement_transversal_items`.

## Absolute rule for future work

- **NEVER REUSE** this directory, in whole or in part, for any future feature, even if the need appears similar or only "for inspiration".
- **NEVER RECONNECT** any of these files (import, route, or MCP tool) to the rest of the application.
- **COMPLETELY IGNORE** this directory when exploring the repository, searching for existing code, or suggesting an architecture. It is no longer part of the product.

If a future project needs a Programme/class/subject/chapter structure, rebuild it entirely from scratch without reusing this code. Ask Bourama explicitly for the required specification again.
