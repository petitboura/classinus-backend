"""Tests de l'import depuis une autre IA (27/10/2026).

Le moteur de chat est remplacé par un faux générateur : on vérifie ici la logique de la tâche
de fond (étapes, fin, échec, reprise, notification), pas la qualité du travail du vrai LLM,
qui ne peut être jugée qu'en conditions réelles.
"""
import sys
import time
from unittest.mock import patch

import types

sys.path.append("core")

# core.notifications ouvre une connexion Supabase à l'import : inutile ici, on la remplace.
_faux_notifications = types.ModuleType("core.notifications")
_faux_notifications.creer_notification = lambda *a, **k: None
sys.modules.setdefault("core.notifications", _faux_notifications)

from core import config_import_ia as cfg  # noqa: E402
from core import import_depuis_autre_ia as imp  # noqa: E402


def _attendre(import_id, user_id, delai=3.0):
    debut = time.time()
    while time.time() - debut < delai:
        etat = imp.lire_etat(import_id, user_id)
        if etat and etat["statut"] != "en_cours":
            return etat
        time.sleep(0.02)
    raise AssertionError("l'import ne s'est pas terminé")


def test_textes_sans_double_tiret_et_complets():
    for langue in ("fr", "en"):
        for t in (cfg.prompt_export(langue), cfg.consigne_llm(langue), cfg.libelle_historique(langue)):
            assert t.strip() and "--" not in t and "\u2014" not in t
        # La liste des applications connectées est toujours demandée, et gardée pour un rappel.
        assert "applications-connectees.md" in cfg.prompt_export(langue)
        assert "applications_a_reconnecter" in cfg.consigne_llm(langue)
    for origine in cfg.ORIGINES:
        assert cfg.PAGES_RESULTAT[origine].startswith("/")
    for cle in ("termine", "echec"):
        for langue in ("fr", "en"):
            titre, corps = cfg.textes_notification(cle, langue)
            assert titre and corps and "--" not in corps


def test_meme_prompt_pour_toutes_les_origines():
    # Un seul prompt et une seule consigne : rien ne dépend de la section d'où part l'utilisateur.
    assert cfg.prompt_export("fr") == cfg.prompt_export("fr")
    assert set(cfg.PAGES_RESULTAT) == set(cfg.ORIGINES)


def test_liens_des_ias():
    ias = {ia["id"]: ia for ia in cfg.ias_export("fr")}
    assert ias["claude"]["prerempli"] is True and ias["claude"]["url"].startswith("https://claude.ai/new?q=")
    assert " " not in ias["claude"]["url"]
    assert ias["gemini"]["prerempli"] is False and "{prompt}" not in ias["gemini"]["url"]


def test_fin_normale_et_notification():
    appels = []

    def faux_chat(**kw):
        appels.append(kw)
        yield {"type": "statut", "texte": "Lecture du zip"}
        yield {"type": "reponse", "texte": "Skills créés : 3."}

    with patch.object(imp, "creer_notification") as notif:
        r = imp.demarrer("u1", "skills", "job-1", "fr", chat_generateur=faux_chat)
        etat = _attendre(r["import_id"], "u1")
    assert etat["statut"] == "termine" and "3" in etat["reponse"]
    assert appels[0]["zips_en_attente"] == ["job-1"] and appels[0]["user_id"] == "u1"
    assert appels[0]["conversation_id"] == r["conversation_id"]
    assert notif.call_args[0][1] == "action_ia_terminee" and notif.call_args.kwargs["lien"] == "/comportements"
    assert appels[0]["message_utilisateur"] == cfg.consigne_llm("fr")


def test_pas_visible_par_un_autre_utilisateur():
    def faux_chat(**kw):
        yield {"type": "reponse", "texte": "ok"}

    with patch.object(imp, "creer_notification"):
        r = imp.demarrer("u2", "chat", "job-2", "en", chat_generateur=faux_chat)
        _attendre(r["import_id"], "u2")
    assert imp.lire_etat(r["import_id"], "autre") is None


def test_confirmation_requise_arrete_sans_approuver():
    def faux_chat(**kw):
        yield {"type": "confirmation_requise", "nom_lisible": "x", "etat_reprise": {}}
        yield {"type": "reponse", "texte": "ne doit pas compter"}

    with patch.object(imp, "creer_notification") as notif:
        r = imp.demarrer("u3", "configuration", "job-3", "fr", chat_generateur=faux_chat)
        etat = _attendre(r["import_id"], "u3")
    assert etat["statut"] == "echec"
    assert notif.call_args[0][2] == cfg.textes_notification("echec", "fr")[0]


def test_reprise_quand_la_limite_d_outils_est_atteinte():
    appels = []

    def faux_chat(**kw):
        appels.append(kw)
        if len(appels) == 1:
            yield {"type": "reponse", "texte": "Début. "}
            yield {"type": "limite_outils_atteinte", "etat_reprise": {"a": 1}}
        else:
            yield {"type": "reponse", "texte": "Fin."}

    with patch.object(imp, "creer_notification"):
        r = imp.demarrer("u4", "skills", "job-4", "fr", chat_generateur=faux_chat)
        etat = _attendre(r["import_id"], "u4")
    assert etat["statut"] == "termine" and etat["reponse"] == "Début. Fin."
    assert appels[1]["reprise"] == {"etat_reprise": {"a": 1}, "type": "continuer_agent"}


def test_exception_donne_un_echec_propre():
    def faux_chat(**kw):
        raise RuntimeError("panne")
        yield

    with patch.object(imp, "creer_notification") as notif:
        r = imp.demarrer("u5", "memoire", "job-5", "fr", chat_generateur=faux_chat)
        etat = _attendre(r["import_id"], "u5")
    assert etat["statut"] == "echec" and notif.called


def test_un_seul_import_actif_par_utilisateur():
    libere = []

    def lent(**kw):
        while not libere:
            time.sleep(0.01)
        yield {"type": "reponse", "texte": "ok"}

    with patch.object(imp, "creer_notification"):
        r = imp.demarrer("u6", "skills", "job-6", "fr", chat_generateur=lent)
        assert imp.import_en_cours("u6") == r["import_id"]
        assert imp.import_en_cours("autre") is None
        libere.append(1)
        _attendre(r["import_id"], "u6")
    assert imp.import_en_cours("u6") is None


if __name__ == "__main__":
    for nom, fn in list(globals().items()):
        if nom.startswith("test_"):
            fn()
            print("ok", nom)
