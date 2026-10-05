"""Éléments de Configuration donnés à l'IA : règles et styles d'office, procédures et comportements retenus en entier."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from configuration_etudiant import (
    PLAFOND_REGLES_STYLES,
    construire_bloc_configuration,
    libelle_categorie,
    separer_config_retenue,
    separer_regles_et_styles,
)


def _el(categorie, texte, nom="", description=""):
    return {"categorie": categorie, "texte": texte, "nom": nom, "description": description}


def test_libelle_categorie():
    assert libelle_categorie(_el("regle", "x")) == "Règle"
    assert libelle_categorie(_el("procedure", "x")) == "Procédure"
    assert libelle_categorie(_el("comportement", "x")) == "Comportement"
    assert libelle_categorie(_el("style", "x")) == "Style"
    assert libelle_categorie(_el(None, "x")) is None


def test_regles_et_styles_sortent_de_la_liste_du_trieur():
    tous = [_el("regle", "r"), _el("style", "s"), _el("procedure", "p"), _el("comportement", "c"), _el(None, "k")]
    regles, styles, autres = separer_regles_et_styles(tous)
    assert [c["texte"] for c in regles] == ["r"]
    assert [c["texte"] for c in styles] == ["s"]
    assert [c["texte"] for c in autres] == ["p", "c", "k"]


def test_config_retenue_separee_des_skills_classiques():
    config, classiques = separer_config_retenue([_el("procedure", "p"), _el(None, "k"), _el("comportement", "c")])
    assert [c["texte"] for c in config] == ["p", "c"]
    assert [c["texte"] for c in classiques] == ["k"]


def test_bloc_vide_sans_configuration():
    assert construire_bloc_configuration(None) == ""
    assert construire_bloc_configuration({"regles": [], "styles": [], "retenus": []}) == ""
    assert construire_bloc_configuration({"regles": [_el("regle", "   ")]}) == ""


def test_bloc_contient_regles_styles_et_retenus_en_entier():
    bloc = construire_bloc_configuration(
        {
            "regles": [_el("regle", "Toujours répondre en français")],
            "styles": [_el("style", "Ton chaleureux")],
            "retenus": [
                _el("procedure", "1. Lire\n2. Corriger", nom="Corriger", description="exercice corrigé"),
                _el("comportement", "Dans tel cas : élève bloqué\nComporte-toi ainsi : reformule", nom="Bloqué"),
            ],
        }
    )
    assert "Toujours répondre en français" in bloc
    assert "Ton chaleureux" in bloc
    assert "Procédure « Corriger » (quand l'utiliser : exercice corrigé)" in bloc
    assert "2. Corriger" in bloc
    assert "Comportement « Bloqué »" in bloc
    assert "reformule" in bloc
    assert "--" not in bloc


def test_plafond_de_regles_et_de_styles():
    regles = [_el("regle", f"regle {i}") for i in range(PLAFOND_REGLES_STYLES + 5)]
    bloc = construire_bloc_configuration({"regles": regles})
    assert f"regle {PLAFOND_REGLES_STYLES - 1}" in bloc
    assert f"regle {PLAFOND_REGLES_STYLES}" not in bloc


def test_texte_trop_long_est_borne():
    bloc = construire_bloc_configuration({"regles": [_el("regle", "a" * 5000)]})
    assert "a" * 1500 in bloc
    assert "a" * 1501 not in bloc


def test_assembler_regle_et_style():
    from configuration_etudiant import assembler_texte_configuration as asm

    assert asm("regle", "  Toujours en français  ") == ("Toujours en français", None)
    assert asm("style", "Ton chaleureux") == ("Ton chaleureux", None)
    assert asm("regle", "   ")[0] is None


def test_assembler_procedure_renumerote():
    from configuration_etudiant import assembler_texte_configuration as asm

    texte, erreur = asm("procedure", "1. Lire l'énoncé\n2) Chercher\n\nRédiger")
    assert erreur is None
    assert texte == "1. Lire l'énoncé\n2. Chercher\n3. Rédiger"
    assert asm("procedure", "\n\n")[0] is None


def test_assembler_comportement_format_de_l_ecran():
    from configuration_etudiant import assembler_texte_configuration as asm

    texte, erreur = asm("comportement", cas="élève bloqué", reaction="reformule la question")
    assert erreur is None
    assert texte == "Dans tel cas : élève bloqué\nComporte-toi ainsi : reformule la question"
    assert asm("comportement", cas="seulement le cas")[0] is None
    assert asm("comportement", reaction="seulement la réaction")[0] is None


def test_assembler_type_inconnu():
    from configuration_etudiant import assembler_texte_configuration as asm

    texte, erreur = asm("skill", "x")
    assert texte is None and "Types valides" in erreur


def test_element_recu_via_un_code_suit_le_meme_chemin():
    # Un élément reçu (id "recu:...") avec son type et son texte est traité
    # comme un élément de l'utilisateur : règle et style d'office.
    recus = [
        {"id": "recu:1", "categorie": "regle", "texte": "Tutoie toujours l'élève", "nom": "", "description": ""},
        {"id": "recu:2", "categorie": "style", "texte": "Phrases courtes", "nom": "", "description": ""},
        {"id": "recu:3", "nom": "Skill classique", "description": "(reçu de X) ..."},
    ]
    regles, styles, autres = separer_regles_et_styles(recus)
    assert [c["id"] for c in regles] == ["recu:1"]
    assert [c["id"] for c in styles] == ["recu:2"]
    assert [c["id"] for c in autres] == ["recu:3"]
    bloc = construire_bloc_configuration({"regles": regles, "styles": styles})
    assert "Tutoie toujours l'élève" in bloc and "Phrases courtes" in bloc
    assert "ceux d'un code qu'il a activé" in bloc
