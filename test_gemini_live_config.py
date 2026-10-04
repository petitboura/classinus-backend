"""
Test manuel des réglages de la voix en direct (core/gemini_live_config.py) :
règles anti-refus, silence, écoute sélective. Aucun appel réseau.
Lancement : python test_gemini_live_config.py
"""

import os

from core.gemini_live_config import reglages_gemini_live


def test_consignes_interdisent_le_refus():
    consignes = reglages_gemini_live()["consignes"]
    assert "aucun droit de refuser" in consignes
    assert "je ne peux pas" in consignes  # cité seulement pour être interdit
    assert "au moindre doute sur ce que Classinus peut faire" in consignes


def test_consignes_decrivent_silence_et_reveil():
    consignes = reglages_gemini_live()["consignes"]
    assert "se_taire" in consignes
    assert "reprendre_la_parole" in consignes
    assert "ne t'est clairement pas adressé" in consignes


def test_descriptions_des_outils_de_silence_presentes():
    reglages = reglages_gemini_live()
    assert reglages["description_outil_silence"].strip()
    assert reglages["description_outil_reveil"].strip()


def test_proactivite_active_par_defaut_et_coupable_par_variable():
    ancien = os.environ.pop("GEMINI_LIVE_PROACTIVITE", None)
    try:
        assert reglages_gemini_live()["proactivite"] is True
        for valeur in ("0", "false", "non", "off", ""):
            os.environ["GEMINI_LIVE_PROACTIVITE"] = valeur
            assert reglages_gemini_live()["proactivite"] is False, valeur
        for valeur in ("1", "true", "oui"):
            os.environ["GEMINI_LIVE_PROACTIVITE"] = valeur
            assert reglages_gemini_live()["proactivite"] is True, valeur
    finally:
        os.environ.pop("GEMINI_LIVE_PROACTIVITE", None)
        if ancien is not None:
            os.environ["GEMINI_LIVE_PROACTIVITE"] = ancien


def test_variable_de_consignes_remplace_toujours_le_defaut():
    os.environ["GEMINI_LIVE_CONSIGNES"] = "autre consigne"
    try:
        assert reglages_gemini_live()["consignes"] == "autre consigne"
    finally:
        os.environ.pop("GEMINI_LIVE_CONSIGNES", None)


def test_consignes_decrivent_arret_definitif_et_reprise():
    consignes = reglages_gemini_live()["consignes"]
    assert "c'est bon" in consignes
    assert "« continue »" in consignes
    assert "reprendra toute seule" in consignes


def test_reglages_de_reprise_de_lecture_presents():
    reglages = reglages_gemini_live()
    assert reglages["annonce_reprise"].strip()
    assert reglages["delai_reprise_ms"] > 0
    assert 0 < reglages["seuil_voix_micro"] < 1


def test_reglages_de_reprise_remplacables_par_variable():
    os.environ["GEMINI_LIVE_DELAI_REPRISE_MS"] = "2500"
    os.environ["GEMINI_LIVE_SEUIL_VOIX_MICRO"] = "0,12"
    os.environ["GEMINI_LIVE_ANNONCE_REPRISE"] = "autre reprise"
    try:
        reglages = reglages_gemini_live()
        assert reglages["delai_reprise_ms"] == 2500
        assert reglages["seuil_voix_micro"] == 0.12
        assert reglages["annonce_reprise"] == "autre reprise"
        os.environ["GEMINI_LIVE_DELAI_REPRISE_MS"] = "pas un nombre"
        os.environ["GEMINI_LIVE_SEUIL_VOIX_MICRO"] = "pas un nombre"
        reglages = reglages_gemini_live()
        assert reglages["delai_reprise_ms"] == 1800
        assert reglages["seuil_voix_micro"] == 0.08
    finally:
        for nom in ("GEMINI_LIVE_DELAI_REPRISE_MS", "GEMINI_LIVE_SEUIL_VOIX_MICRO", "GEMINI_LIVE_ANNONCE_REPRISE"):
            os.environ.pop(nom, None)


if __name__ == "__main__":
    for nom, fonction in sorted(globals().items()):
        if nom.startswith("test_") and callable(fonction):
            fonction()
            print("OK", nom)
