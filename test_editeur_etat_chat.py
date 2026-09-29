"""Régressions du transport de l'état de l'éditeur vers le chat IA."""

from unittest.mock import patch

from api.chat import EnvoyerMessagePayload
import construction_system_prompt as csp


def test_payload_chat_accepte_etat_editeur():
    payload = EnvoyerMessagePayload(
        message="corrige mon code",
        agent_id="clovis",
        canal_en_direct=True,
        etat_editeur={
            "langage": "python",
            "nom_fichier": "main.py",
            "plein_ecran": False,
            "code": "print(1)",
            "derniere_execution": {"lignes": ["1"], "erreur": None},
        },
    )

    assert payload.etat_editeur["code"] == "print(1)"


def test_etat_editeur_du_tour_est_prioritaire_sur_le_websocket():
    etat_frais = {
        "langage": "python",
        "nom_fichier": "main.py",
        "plein_ecran": True,
        "code": "print('frais')",
        "derniere_execution": {"lignes": ["frais"], "erreur": None},
    }
    etat_websocket_obsolete = {
        "langage": "javascript",
        "nom_fichier": "ancien.js",
        "plein_ecran": False,
    }

    with patch.object(csp, "get_system_prompt", return_value="PROMPT_BASE"), patch.object(
        csp, "obtenir_etat_editeur", return_value=etat_websocket_obsolete
    ):
        prompt = csp._construire_system_prompt(
            "corrige mon code",
            "agent-test",
            user_id="u1",
            etat_editeur=etat_frais,
        )

    assert "main.py" in prompt
    assert "python" in prompt
    assert "ancien.js" not in prompt
    assert "javascript" not in prompt


def test_ancien_appelant_sans_etat_editeur_utilise_le_cache_websocket():
    etat_websocket = {
        "langage": "python",
        "nom_fichier": "cache.py",
        "plein_ecran": False,
    }

    with patch.object(csp, "get_system_prompt", return_value="PROMPT_BASE"), patch.object(
        csp, "obtenir_etat_editeur", return_value=etat_websocket
    ):
        prompt = csp._construire_system_prompt(
            "lis mon code",
            "agent-test",
            user_id="u1",
        )

    assert "cache.py" in prompt
    assert "python" in prompt
