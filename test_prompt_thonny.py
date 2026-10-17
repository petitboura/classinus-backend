"""Le prompt du client Thonny n'a plus les consignes d'affichage du site, le site reste inchangé."""

from unittest.mock import patch

import construction_system_prompt as csp
import prompt_thonny


def _prompt(**kwargs):
    with patch.object(csp, "get_system_prompt", return_value="IDENTITE_AGENT"):
        return csp._construire_system_prompt("bonjour", "agent-test", user_id="u1", **kwargs)


def test_client_thonny_sans_consignes_d_affichage_du_site():
    prompt = _prompt(client="thonny", libelles_client={"envoyer_code": "Envoyer mon code"})

    assert "IDENTITE_AGENT" in prompt
    assert "Envoyer mon code" in prompt
    assert "<memoire_eleve>" in prompt
    for absent in ("mermaid", "```qcm", "```fiche", "<formats_enrichis>", "<etat_application>", "carte à part"):
        assert absent not in prompt


def test_client_thonny_chaque_section_une_seule_fois():
    prompt = _prompt(client="thonny")

    for balise in ("<liens>\n", "<recherche_documents>\n", "<outils_generation_action>\n", "<faits_verifiables>\n", "<appels_outils>\n"):
        assert prompt.count("\n" + balise) == 1


def test_site_garde_ses_consignes_d_affichage():
    for client in (None, "autre"):
        prompt = _prompt(client=client)
        assert "<formats_enrichis>" in prompt
        assert "```mermaid```" in prompt


def test_libelles_inconnus_ou_dangereux_sont_ignores():
    propres = prompt_thonny.libelles_valides({"envoyer_code": "A {b}\n`c`", "inconnu": "x", "copier": 3})

    assert propres == {"envoyer_code": "A b c"}
