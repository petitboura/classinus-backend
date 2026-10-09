"""Les quatre règles de vision de l'écran sont fixes : elles partent à chaque message.

Règle posée par Bourama : l'IA doit tout voir à l'écran, nommer chaque bouton,
ouvrir un panneau avant de cliquer derrière lui, savoir ce que fait un bouton
agrandir, et lire tous les panneaux. Ce test empêche qu'un changement du prompt
retire ces règles ou les rende dépendantes d'une condition.
"""

from unittest.mock import patch

import construction_system_prompt as csp

MARQUEURS = [
    "<vision_ecran>",
    "Ne dis jamais « un certain bouton »",
    "ouvre d'abord ce panneau",
    "Fenêtre flottante",
    "(« agrandit … »)",
    "toutes les fenêtres et tous les panneaux affichés",
]


def _prompt(**kwargs):
    with patch.object(csp, "get_system_prompt", return_value="PROMPT_BASE"), patch.object(
        csp, "obtenir_etat_editeur", return_value=None
    ):
        return csp._construire_system_prompt("bonjour", "agent-test", **kwargs)


def test_regles_presentes_sans_liste_ecran_ni_compte():
    prompt = _prompt()
    for marqueur in MARQUEURS:
        assert marqueur in prompt


def test_regles_presentes_avec_liste_ecran_et_compte():
    actions = [{"id": "el-1", "description": "Page, Envoyer"}]
    prompt = _prompt(user_id="u1", actions_ecran=actions)
    for marqueur in MARQUEURS:
        assert marqueur in prompt


def test_regles_presentes_avec_liste_ecran_vide():
    prompt = _prompt(user_id="u1", actions_ecran=[])
    for marqueur in MARQUEURS:
        assert marqueur in prompt


def test_une_ligne_longue_garde_la_fin_de_sa_description():
    fin = "(agrandit « Éditeur de code »)"
    description = "Fenêtre flottante « Éditeur », bouton sans texte, icône « maximize », en haut à droite " + fin
    assert 100 < len(description) < csp.LONGUEUR_MAX_LIGNE_ACTION
    prompt = _prompt(user_id="u1", actions_ecran=[{"id": "el-9", "description": description}])
    assert fin in prompt
