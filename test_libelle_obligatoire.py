"""Le texte des lignes d'outils est obligatoire pour l'IA (26/11/2026), sauf contrainte chez Groq."""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

import libelles_activite_ia as libelles  # noqa: E402

CHAMP = libelles.PARAMETRE_LIBELLE_OUTIL


def _outil(nom, parametres):
    return {"type": "function", "function": {"name": nom, "parameters": parametres}}


def test_champ_requis_sans_toucher_a_l_original():
    original = _outil("recherche_web", {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]})
    envoye = libelles.outils_avec_libelle([original])[0]["function"]["parameters"]
    assert envoye["required"] == [CHAMP, "q"]
    assert original["function"]["parameters"]["required"] == ["q"]
    assert CHAMP not in original["function"]["parameters"]["properties"]


def test_champ_deja_present_devient_requis_une_seule_fois():
    deja = _outil("x", libelles.schema_avec_libelle({}))
    premier = libelles.outils_avec_libelle([deja])
    second = libelles.outils_avec_libelle(premier)
    assert second[0]["function"]["parameters"]["required"] == [CHAMP]


def test_groq_garde_la_consigne_sans_la_contrainte():
    outil = _outil("x", {"type": "object", "properties": {}})
    envoye = libelles.outils_avec_libelle([outil], obligatoire=False)[0]["function"]["parameters"]
    assert CHAMP not in envoye.get("required", [])
    assert envoye["properties"][CHAMP]["description"].startswith("REQUIRED")


def test_outils_internes_sans_champ():
    for nom in ("garder_outils", "commenter"):
        outil = _outil(nom, {"type": "object", "properties": {}})
        assert libelles.outils_avec_libelle([outil]) == [outil]


def _champs_requis_envoyes_par_la_boucle(client_est_groq):
    """Joue le vrai appel de clôture de la boucle et renvoie les champs requis envoyés au modèle."""
    os.environ.setdefault("SUPABASE_URL", "http://localhost")
    os.environ.setdefault("SUPABASE_SECRET", "test")
    import boucle_agent

    recu = {}

    def creer(**arguments):
        recu.update(arguments)
        return iter(())

    client = boucle_agent.Groq(api_key="cle") if client_est_groq else types.SimpleNamespace()
    client.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=creer))
    outil = _outil("x", {"type": "object", "properties": {}})
    list(boucle_agent._generer_conclusion_forcee(client, [{"role": "user", "content": "a"}], [outil], "modele", {}, 5))
    return recu["tools"][0]["function"]["parameters"].get("required", [])


def test_la_boucle_exige_le_champ_sauf_chez_groq():
    assert _champs_requis_envoyes_par_la_boucle(client_est_groq=False) == [CHAMP]
    assert _champs_requis_envoyes_par_la_boucle(client_est_groq=True) == []
