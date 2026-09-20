"""
Audit complet du Bureau (20/09/2026, demande Bourama) : tableau de bord
d'un code de partage, en plus de l'audit hebdomadaire des signalements
déjà existant (core/audit_hebdomadaire_corrections.py, non touché ici,
resté à part -- brique de logique distincte).

Phase 1 (validée par Bourama, les points plus lourds -- temps
d'utilisation, niveau étudiant, notions demandées -- sont à revoir plus
tard car ils demandent un nouveau suivi qui n'existe pas encore) :
- rattachés actifs (ont envoyé au moins un message avec ce code, jamais
  de seuil de récence) vs inactifs
- signalements non traités (même définition que l'audit hebdomadaire :
  "correction" et "signalement" sont la même chose depuis la refonte du
  10/09/2026, donc un seul chiffre)
- nombre total de conversations et de questions (messages élève)
- heures de pointe (grille jour de la semaine x heure) + jour le plus
  fréquenté, calculés sur les messages ÉLÈVE uniquement (role="user") --
  reflète quand les élèves utilisent réellement le code, pas quand
  l'IA répond
- outils les plus utilisés (déjà stocké par message dans
  historique_conversations.meta["outils"], voir core/boucle_agent.py,
  chantier du 15/09 -- rien de nouveau à tracker)
- visuels/affichages les plus utilisés (détectés dans le contenu des
  réponses de l'IA, via les blocs ```type``` reconnus par
  components/chat/BulleMessage.tsx côté frontend -- liste tenue à jour
  manuellement ici, à mettre à jour si un nouveau type de bloc apparaît
  côté frontend)
- modes pédagogiques les plus choisis (Socratique/Professeur/Tuteur/
  Examinateur, voir SelecteurPersonaPedagogique.tsx et la table
  conversation_persona_pedagogique côté backend)

Le lien conversation -> code passe par conversation_mode_actif
(rattachement_id) -> rattachements_codes (code_id), voir
core/codes_partage.py.
"""

import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone

from supabase import create_client

from api.historique import _recuperer_toutes_les_lignes, TAILLE_PAGE_SUPABASE
from core.erreurs import erreur_api

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET = os.environ.get("SUPABASE_SECRET")
supabase = create_client(SUPABASE_URL, SUPABASE_SECRET)

JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Liste tenue à jour manuellement à partir du switch(langage) de
# components/chat/BulleMessage.tsx -- seuls les blocs qui produisent un
# VRAI visuel (pas ```html```/```widget```, regroupés ensemble, ni un
# bloc de code générique, qui n'est pas un "affichage" au sens de cette
# demande).
TYPES_VISUELS: dict[str, str] = {
    "mermaid": "Diagramme (Mermaid)",
    "chart": "Graphique de données",
    "carte": "Carte interactive",
    "geometrie": "Schéma géométrique",
    "qcm": "QCM interactif",
    "question": "Question interactive",
    "fiche": "Fiche de révision",
    "widget": "Widget interactif",
    "html": "Widget interactif",
}

# Mode pédagogique choisi par l'élève (20/09/2026, demande Bourama, voir
# la barre de saisie -- SelecteurPersonaPedagogique.tsx côté frontend),
# mêmes clés que MODES_PEDAGOGIQUES (core/profils_agents.py) et
# PERSONAS_VALIDES (core/persona_pedagogique_conversation.py).
LABELS_PERSONAS: dict[str, str] = {
    "socratique": "Socratique",
    "professeur": "Professeur",
    "tuteur": "Tuteur",
    "examinateur": "Examinateur",
}

# Mode source choisi par l'élève (20/09/2026, demande Bourama : "ajouter
# l'analytique des modes recherche et sur pièces" -- même panneau que le
# persona pédagogique dans la barre de saisie, groupe séparé). Mêmes clés
# que MODES_SOURCE_VALIDES (core/mode_source_conversation.py). "Aucun"
# (mode_source=None) n'est pas dans ce dict : pas de ligne comptée pour
# ce cas, comme pour les personas.
LABELS_MODES_SOURCE: dict[str, str] = {
    "recherche": "Recherche",
    "sur_pieces": "Sur pièces",
}

# Outils à exclure de "outils les plus utilisés" (20/09/2026, demande
# explicite Bourama) : des vérifications/mécanismes internes, pas de
# vrais choix de l'élève, qui dominent le classement sans rien dire
# d'utile. Comparé au nom technique (nomOutil), pas au label affiché,
# pour rester robuste si le label change.
# - verifier_consignes_code_actif : appel forcé à quasiment chaque
#   message dès qu'un code est actif (voir
#   core/outils_verification_code_actif.py)
# - demander_outils : recherche interne dans le catalogue d'outils
# - gerer_base_connaissance : recherche dans la base de connaissances
#   de Classinus -- pas un mécanisme forcé, mais jugé par Bourama plus
#   proche d'un mécanisme interne que d'un vrai choix d'outil ici
# - consulter_skills_chapitres_matiere : étape câblée en dur dans
#   core/main.py (nom_outil_niveau2), déclenchée automatiquement, sans
#   aucune décision du modèle
# gerer_document_bibliotheque n'est PAS exclu (retour en arrière,
# 20/09/2026) : Bourama voulait une analytique séparée des modes source
# Recherche/Sur pièces (voir LABELS_MODES_SOURCE ci-dessus), pas
# l'exclusion de cet outil -- mauvaise interprétation corrigée.
OUTILS_EXCLUS_DU_TOP: frozenset[str] = frozenset({
    "verifier_consignes_code_actif",
    "demander_outils",
    "gerer_base_connaissance",
    "consulter_skills_chapitres_matiere",
})

_MOTIF_BLOC = re.compile(r"```(\w+)")


def _verifier_code_appartient(code_id: str, prof_id: str) -> None:
    try:
        res = (
            supabase.table("codes_partage")
            .select("id")
            .eq("id", code_id)
            .eq("proprietaire_id", prof_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (vérification propriétaire code {code_id}) : {e}")
        raise erreur_api(500, "ERREUR_INCONNUE")
    if not res or not res.data:
        raise erreur_api(404, "NOTION_PROGRAMME_CODE_INTROUVABLE")


def _rattachements_du_code(code_id: str) -> list[dict]:
    try:
        res = supabase.table("rattachements_codes").select("id, receveur_id").eq("code_id", code_id).execute()
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (lecture rattachements du code {code_id}) : {e}")
        return []
    return res.data or []


def _conversations_du_code(rattachement_ids: list[str]) -> list[dict]:
    """{conversation_id, user_id} pour toutes les conversations qui ont eu
    ce code actif à un moment (conversation_mode_actif), paginé."""
    if not rattachement_ids:
        return []
    return _recuperer_toutes_les_lignes(
        lambda: supabase.table("conversation_mode_actif")
        .select("conversation_id, user_id")
        .in_("rattachement_id", rattachement_ids)
    )


def _messages_des_conversations(conversation_ids: list[str]) -> list[dict]:
    if not conversation_ids:
        return []
    toutes_les_lignes: list = []
    # in_() Supabase/PostgREST a une limite pratique de taille d'URL --
    # découpé en blocs de TAILLE_PAGE_SUPABASE id à la fois, chaque bloc
    # lui-même paginé par _recuperer_toutes_les_lignes.
    for debut in range(0, len(conversation_ids), TAILLE_PAGE_SUPABASE):
        bloc_ids = conversation_ids[debut : debut + TAILLE_PAGE_SUPABASE]
        toutes_les_lignes.extend(
            _recuperer_toutes_les_lignes(
                lambda bloc_ids=bloc_ids: supabase.table("historique_conversations")
                .select("role, content, created_at, meta")
                .in_("conversation_id", bloc_ids)
            )
        )
    return toutes_les_lignes


def _signalements_non_traites(code_id: str) -> int:
    try:
        res = (
            supabase.table("signalements")
            .select("id", count="exact")
            .eq("code_id", code_id)
            .eq("statut", "nouveau")
            .execute()
        )
    except Exception as e:
        logging.error(f"ERREUR SUPABASE (signalements non traités code {code_id}) : {e}")
        return 0
    return res.count or 0


def _personas_des_conversations(conversation_ids: list[str]) -> list[dict]:
    if not conversation_ids:
        return []
    toutes_les_lignes: list = []
    for debut in range(0, len(conversation_ids), TAILLE_PAGE_SUPABASE):
        bloc_ids = conversation_ids[debut : debut + TAILLE_PAGE_SUPABASE]
        toutes_les_lignes.extend(
            _recuperer_toutes_les_lignes(
                lambda bloc_ids=bloc_ids: supabase.table("conversation_persona_pedagogique")
                .select("persona")
                .in_("conversation_id", bloc_ids)
            )
        )
    return toutes_les_lignes


def _modes_source_des_conversations(conversation_ids: list[str]) -> list[dict]:
    if not conversation_ids:
        return []
    toutes_les_lignes: list = []
    for debut in range(0, len(conversation_ids), TAILLE_PAGE_SUPABASE):
        bloc_ids = conversation_ids[debut : debut + TAILLE_PAGE_SUPABASE]
        toutes_les_lignes.extend(
            _recuperer_toutes_les_lignes(
                lambda bloc_ids=bloc_ids: supabase.table("conversation_mode_source")
                .select("mode_source")
                .in_("conversation_id", bloc_ids)
            )
        )
    return toutes_les_lignes


def _heure_locale(horodatage: str) -> datetime | None:
    if not horodatage:
        return None
    try:
        return datetime.fromisoformat(horodatage.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def calculer_audit_complet(prof_id: str, code_id: str) -> dict:
    _verifier_code_appartient(code_id, prof_id)

    rattachements = _rattachements_du_code(code_id)
    total_rattaches = len(rattachements)
    rattachement_ids = [r["id"] for r in rattachements]
    receveurs_ids = {r["receveur_id"] for r in rattachements}

    conversations = _conversations_du_code(rattachement_ids)
    conversation_ids = list({c["conversation_id"] for c in conversations if c.get("conversation_id")})
    actifs_ids = {c["user_id"] for c in conversations if c.get("user_id")} & receveurs_ids
    actifs = len(actifs_ids)
    inactifs = max(total_rattaches - actifs, 0)

    messages = _messages_des_conversations(conversation_ids)
    questions_total = sum(1 for m in messages if m.get("role") == "user")

    grille = [[0] * 24 for _ in range(7)]
    for m in messages:
        if m.get("role") != "user":
            continue
        horodatage = _heure_locale(m.get("created_at"))
        if horodatage is None:
            continue
        grille[horodatage.weekday()][horodatage.hour] += 1

    totaux_par_jour = [sum(ligne) for ligne in grille]
    jour_plus_frequente = None
    if any(totaux_par_jour):
        jour_plus_frequente = JOURS_SEMAINE[totaux_par_jour.index(max(totaux_par_jour))]

    compteur_outils: Counter = Counter()
    for m in messages:
        for outil in (m.get("meta") or {}).get("outils") or []:
            if outil.get("nomOutil") in OUTILS_EXCLUS_DU_TOP:
                continue
            nom = outil.get("nomLisible") or outil.get("nomOutil")
            if nom:
                compteur_outils[nom] += 1

    compteur_visuels: Counter = Counter()
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for langage in _MOTIF_BLOC.findall(m.get("content") or ""):
            label = TYPES_VISUELS.get(langage.lower())
            if label:
                compteur_visuels[label] += 1

    compteur_personas: Counter = Counter()
    for p in _personas_des_conversations(conversation_ids):
        label = LABELS_PERSONAS.get((p.get("persona") or "").lower())
        if label:
            compteur_personas[label] += 1

    compteur_modes_source: Counter = Counter()
    for m2 in _modes_source_des_conversations(conversation_ids):
        label = LABELS_MODES_SOURCE.get((m2.get("mode_source") or "").lower())
        if label:
            compteur_modes_source[label] += 1

    return {
        "total_rattaches": total_rattaches,
        "actifs": actifs,
        "inactifs": inactifs,
        "conversations_total": len(conversation_ids),
        "questions_total": questions_total,
        "signalements_non_traites": _signalements_non_traites(code_id),
        "heures_pointe": {
            "jours": JOURS_SEMAINE,
            "grille": grille,
            "jour_plus_frequente": jour_plus_frequente,
        },
        "outils_top": [{"nom": nom, "nombre": n} for nom, n in compteur_outils.most_common(8)],
        "visuels_top": [{"nom": nom, "nombre": n} for nom, n in compteur_visuels.most_common(8)],
        "modes_top": [{"nom": nom, "nombre": n} for nom, n in compteur_personas.most_common(4)],
        "modes_source_top": [{"nom": nom, "nombre": n} for nom, n in compteur_modes_source.most_common(2)],
    }
