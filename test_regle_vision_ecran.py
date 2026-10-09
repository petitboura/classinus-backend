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


# Lecture de l'écran du PC (lire_ecran et état envoyé en continu) : tout élément
# reste désignable, même sans nom, et un bouton agrandir dit ce qu'il agrandit.

def _formater(element, titre=None):
    from core import outils_action_agent_pc as outils

    return outils._formater_element_lu(element, titre)


def test_bouton_sans_nom_reste_designable():
    ligne = _formater({"type": "bouton", "nom": "", "id_auto": "btnPanel", "aide": "Ouvrir le panneau", "x": 10, "y": 20})
    assert "sans nom" in ligne
    assert "btnPanel" in ligne and "Ouvrir le panneau" in ligne
    assert "clic possible en (10, 20)" in ligne


def test_bouton_agrandir_dit_la_fenetre_depuis_la_barre_de_titre():
    ligne = _formater({"type": "bouton", "nom": "Agrandir", "panneau": "Barre de titre", "x": 1, "y": 2}, "Bloc-notes")
    assert "agrandit la fenêtre « Bloc-notes »" in ligne


def test_bouton_agrandir_dit_le_panneau_qui_le_contient():
    ligne = _formater({"type": "bouton", "nom": "Plein écran", "panneau": "Aperçu", "x": 1, "y": 2}, "Thonny")
    assert "agrandit le panneau « Aperçu »" in ligne


def test_bouton_agrandir_dans_une_fenetre_flottante():
    ligne = _formater({"type": "bouton", "nom": "Agrandir", "zone": "fenêtre flottante « Aide »", "x": 1, "y": 2})
    assert "agrandit la fenêtre flottante « Aide »" in ligne
    assert "dans la fenêtre flottante « Aide »" in ligne


def test_lecture_longue_garde_les_boutons_apres_beaucoup_de_texte():
    from core import outils_action_agent_pc as outils

    elements = [{"type": "bouton", "nom": f"Bouton {i}", "x": i, "y": i} for i in range(150)]
    resultat = {"mode": "uia", "titre_fenetre_active": "Appli", "elements": elements}
    texte = outils._formater_lecture_ecran(resultat)
    assert "Bouton 149" in texte
    assert "Lecture coupée" not in texte
