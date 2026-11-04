# Project: new student product (Clovis)

[English version] · [Français](chantier-programme-etudiant.fr.md)

---

## Part 1: Programme structure (context for Parts 2 and 3)

- Hierarchy: **Programme** (by class/grade) → **subjects** → **chapters**.
- "Grade" is an organizational relationship only, not an access-control rule.
- Attached practical content: **documents** and **exercises** (each linked to one chapter), **exams/assignments** (many-to-many relationship with chapters).
- An additional cross-cutting classification (semester, year, free-form section) applies to subjects, chapters, documents, exercises, and exams.
- Goal: give the AI a structured framework so it never generates content outside the Programme or grade, while still allowing on-demand generation.

*(Implementation was already present in `clovis-backend`: tables `programmes`, `matieres`, `chapitres`, `documents_programme`, `exercices_programme`, `examens_programme`, `examen_chapitres`, `classements_transversaux`, `classement_transversal_items`, and the plugin system `plugins_programme` / `plugin_telechargements`. For full details on per-subject/chapter content limits, the plugin system, and its business model, see migrations `2026_08_12_*` and `2026_08_14_plugin_examens_transverses.sql`.)*

---

## Part 2: a Notion-like section integrated into the app

### Principle

- A section inside the existing app (Clovis), **not a separate application**.
- Inspired by Notion but **simplified** to include only features useful to researchers.
- No separate researcher and student audiences. Students are researchers too, in the sense of research, organization, and synthesis. One tool serves both; there is no separate researcher workspace.

### Relationship with the rest of the app

- This section is **not merged into** the rest of the app. It remains distinct.
- It is nevertheless linked: a page can describe or reference where content lives elsewhere in the app (for example, a chapter or document). This lets users find everything from one page rather than navigating between separate storage areas.
- Goal: **centralize access** and provide a single entry point.
- A link/reference page is itself a page in the Notion-like section, independent of other pages in that section. There are two page types: regular content pages and "hub" pages that point to other locations, typically the Programme structure from Part 1.

### Research: how students actually use Notion

Key features to retain:

- One page per subject, with subpages for courses, homework, projects, and revision.
- Revision databases (tables/lists) to track progress, with multiple views: list, table, calendar, and Kanban.
- Support for mathematical equations and LaTeX symbols, especially useful for science subjects.
- Task management: prioritize homework and create subtasks for each project.
- Spaced repetition for revision over several weeks, a real differentiator of the best student Notion templates.
- Smooth collaboration between classmates and centralized resources.

Features to exclude because they are too complex for the simplicity goal:

- Advanced relational databases, third-party widgets, and external integrations (Google Calendar, weather, Twitter feeds, etc.).
- Paid template marketplace (up to $19 on Notion). In Clovis, the plugin system from Part 1 already covers this role.

Key point: Notion already gives students its paid plan for free with a university email address. Therefore, the differentiator is not price. It is **immediate simplicity** (zero setup, unlike Notion where relational configuration takes time even for an experienced user) and the fact that **the tool is already part of the ecosystem** (no new account, natively connected to the class/subject/chapter structure from Part 1).

---

## Part 3: AI agent with device control

### General principle

Scope: what the student explicitly authorizes and requests. Permission layers, in order:

1. What the application permits internally.
2. What the operating system permits.
3. Any additional permission explicitly granted by the user.

### Phone (simplified, updated approach)

The original idea of full phone control like an "autonomous agent" (Accessibility Service and screen clicks) is abandoned because of the risk of rejection by Google Play.

The new approach uses only official, lightweight mechanisms and never uses the Accessibility API.

**Capabilities to add, without introducing this broad-access risk**

*Monitoring and information*

- See time spent in each app (usage history).
- Know which app is currently active (using the same mechanism as screen-time tracking).
- Browse, edit, add, classify, and create folders/files, but only inside folders explicitly selected by the student once. The selection persists; access must not be requested again for every operation.

*Actions and reminders*

- Send standard notifications.
- Open an app on request.
- Full-screen notifications are possible, but should be reserved for alarm/important-reminder use cases to stay within Google review requirements.
- Create reminders/alarms through the native clock app.
- Create and read calendar events.
- Enable/disable Do Not Disturb during a session.
- Adjust volume/ringer during a session.

*Classinus acting on behalf of the student*

- Allow Classinus to use a third-party app through that app's own API or an MCP connector (such as Notion, Google Calendar, Gmail, and Drive), following the same principle as current Claude connectors. This works only for apps that expose a public API/MCP, not personal Instagram, TikTok, or WhatsApp accounts.

**Explicitly out of scope**

- Remotely close another app: technically impossible, not merely risky.
- Block/unblock access to an app: same technical limitation.
- Click or fill in fields in other apps: requires Accessibility access and has been excluded from the beginning.
- Access every file on the phone without explicit folder selection: reserved for file managers and very likely to be rejected by Google Play.
- Automatically detect a new folder added elsewhere on the phone (outside designated folders): blocked by the operating system itself. There is no workaround without the broad access described above, which has been rejected.

**Shared mechanism for file/folder access**

The student always initiates access. Classinus may offer to request access to another folder, but the student chooses it through the system picker. Once granted, access persists and does not need to be reconfirmed each time. This follows the same idea as pairing devices, similar to WhatsApp Web.

### PC / desktop (unchanged)

- Technically simpler than mobile: Windows, macOS, and Linux have more open and mature automation APIs, no App Store restrictions, and less restrictive sandboxes.
- Use a computer-use model similar to Claude Cowork: an agent that controls mouse, keyboard, files, and apps with the user's permission.

### Decision: one unified agent (unchanged)

- **One "brain"** shared by phone and PC: understanding, planning, reasoning, permission enforcement, and context memory.
- **Two different "hands":** on phone, use only the official mechanisms described above (no Accessibility); on PC, use conventional desktop automation.
- Benefits: a consistent product experience, simpler maintenance (one reasoning improvement benefits both platforms), and possible continuity across devices.

### Device linking (unchanged)

Requirement: the user can stay on PC and have an action performed on the phone, and vice versa.

Two linking options were evaluated:

| Option | Security | Behavior |
|---|---|---|
| **Automatic account linking** | Higher risk | Devices are linked as soon as the same account signs in on both. This creates a single point of failure: if the account is compromised remotely (phishing or a stolen session), an attacker controls both devices without any additional check. |
| **Explicit pairing** | Safer (recommended) | Scan a code or confirm on both devices when linking. It requires physical access to an already linked device, so a remotely stolen account alone cannot complete the pairing. |

**Selected recommendation:** require explicit pairing **once**, when creating the link (like WhatsApp Web: scan once, remain linked until manually revoked). Do not require confirmation before every action, so the feature remains practical for daily use.

---

*Document generated from project-planning sessions: the Clovis project, separate from the Djiguignè repositories.*
