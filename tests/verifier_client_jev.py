"""
Client Jev du canal en direct (09/10/2026, chantier Jev, lot 2).

Aucun reseau, aucune cle reelle : httpx.MockTransport rejoue les formats exacts
de la documentation officielle (docs.typesafe.ai, API reference). Verifie :
- la requete : adresse, en-tete Authorization, corps (state, model, questions)
  et serialisation de chaque type de question ;
- la lecture des reponses Choice, Score et Noul au format officiel ;
- les erreurs : 401 et 422 sans reessai, 429 puis succes, 529 repetes jusqu'a
  l'echec, reseau coupe, delai depasse ;
- les protections : options a 255 maximum, niveaux de Score de 2 a 10, state
  trop long, option inconnue renvoyee par le serveur, reponse manquante ou d'un
  mauvais type ;
- la confidentialite : ni la cle ni le state dans les messages d'erreur ;
- creer_client_depuis_env : None sans cle.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from core import client_jev as jev
from core.client_jev import Choice, JevClient, JevErreur, JevEtatTropLong, JevIndisponible, Noul, Score

CLE = "cle-secrete-de-test-1234"
STATE_SECRET = "Texte prive affiche a l'ecran de l'etudiant : rendez-vous chez le medecin"

QUESTIONS = {
    "action": Choice(
        instructions="Quelle action faire ensuite ?",
        criteria={"a1": "Cliquer sur Enregistrer", "a2": "Cliquer sur Annuler", "escalade": None},
    ),
    "importance": Score(instructions="Importance du commentaire", criteria=("Au passage", "Notable", "Critique")),
    "terminee": Noul(instructions="La tache est-elle terminee ?"),
}

# Reponse au format officiel de la documentation.
REPONSE_OK = {
    "model": "jev-1.13.0",
    "answers": {
        "action": {"type": "choice", "choice": "a1", "confidence": 0.78,
                   "probabilities": {"a1": 0.85, "a2": 0.0, "escalade": 0.15}},
        "importance": {"type": "score", "score": 1.05, "confidence": 0.92,
                       "legend": {"0": "Au passage", "1": "Notable", "2": "Critique"},
                       "probabilities": {"0": 0.0, "1": 0.95, "2": 0.05}},
        "terminee": {"type": "noul", "noul": 0.04},
    },
    "usage": {"input_tokens": 392, "output_tokens": 65},
}


def client(gestionnaire, **options):
    attentes = []

    async def dormir(secondes):
        attentes.append(secondes)

    c = JevClient(CLE, transport=httpx.MockTransport(gestionnaire), dormir=dormir, **options)
    c.attentes = attentes
    return c


async def erreur_de(coroutine):
    try:
        await coroutine
    except JevErreur as e:
        return e
    raise AssertionError("une JevErreur etait attendue")


async def verifier_requete_et_reponse():
    vues = []

    def gestionnaire(requete: httpx.Request):
        vues.append(requete)
        return httpx.Response(200, json=REPONSE_OK)

    async with client(gestionnaire) as c:
        reponse = await c.evaluer(STATE_SECRET, QUESTIONS)

    assert len(vues) == 1, "une seule requete par tour"
    requete = vues[0]
    assert requete.method == "POST" and str(requete.url) == "https://api.typesafe.ai/v1/systemone", requete.url
    assert requete.headers["authorization"] == f"Bearer {CLE}"
    corps = json.loads(requete.content)
    assert set(corps) == {"state", "model", "questions"}, corps.keys()
    assert corps["state"] == STATE_SECRET and corps["model"] == "jev-1.13.0"
    assert corps["questions"]["action"] == {
        "type": "choice", "instructions": "Quelle action faire ensuite ?",
        "criteria": {"a1": "Cliquer sur Enregistrer", "a2": "Cliquer sur Annuler", "escalade": None},
    }
    assert corps["questions"]["importance"]["criteria"] == ["Au passage", "Notable", "Critique"]
    assert corps["questions"]["terminee"] == {"type": "noul", "instructions": "La tache est-elle terminee ?"}, "pas de criteria vide"

    assert reponse.modele == "jev-1.13.0" and (reponse.tokens_entree, reponse.tokens_sortie) == (392, 65)
    choix = reponse.choice("action")
    assert (choix.choix, choix.confiance) == ("a1", 0.78) and choix.probabilites["a1"] == 0.85
    score = reponse.score("importance")
    assert score.score == 1.05 and score.confiance == 0.92 and score.legende["2"] == "Critique"
    noul = reponse.noul("terminee")
    assert noul.valeur == 0.04 and abs(jev.confiance_noul(noul) - 0.92) < 1e-9
    assert abs(jev.confiance_noul(jev.ReponseNoul(0.5))) < 1e-9 and jev.confiance_noul(jev.ReponseNoul(1.0)) == 1.0

    # Mauvais type demande : erreur claire.
    try:
        reponse.score("action")
    except JevErreur:
        pass
    else:
        raise AssertionError("un getter du mauvais type doit lever")

    # Noul avec criteres : transmis tels quels.
    corps_noul = Noul("Question", criteria={"true": "oui", "false": "non"}).vers_json()
    assert corps_noul["criteria"] == {"true": "oui", "false": "non"}
    # State structure (objet) accepte.
    async with client(lambda r: httpx.Response(200, json=REPONSE_OK)) as c:
        await c.evaluer({"objectif": "x", "actions": [1, 2]}, QUESTIONS)


async def verifier_erreurs_http():
    # 401 et 422 : refus definitif, aucun reessai, extrait du serveur dans le message.
    for statut, texte in ((401, "Invalid API key"), (422, "questions.action.criteria: required")):
        appels = []

        def gestionnaire(requete, statut=statut, texte=texte):
            appels.append(1)
            return httpx.Response(statut, text=texte)

        async with client(gestionnaire) as c:
            e = await erreur_de(c.evaluer("s", QUESTIONS))
        assert not isinstance(e, JevIndisponible) and e.statut == statut, e
        assert len(appels) == 1 and c.attentes == [], "pas de reessai sur un refus"
        assert texte in str(e)

    # 429 puis succes : un reessai silencieux, avec attente.
    sequence = iter([httpx.Response(429, headers={"retry-after": "1"}), httpx.Response(200, json=REPONSE_OK)])
    async with client(lambda r: next(sequence)) as c:
        reponse = await c.evaluer("s", QUESTIONS)
        assert reponse.choice("action").choix == "a1"
        assert len(c.attentes) == 1 and 0 < c.attentes[0] <= jev.ATTENTE_REESSAI_MAX_SECONDES

    # 529 en continu : echec apres 1 + 2 tentatives, avec attentes croissantes bornees.
    appels = []

    def surcharge(requete):
        appels.append(1)
        return httpx.Response(529, text="overloaded")

    async with client(surcharge) as c:
        e = await erreur_de(c.evaluer("s", QUESTIONS))
    assert isinstance(e, JevIndisponible) and e.statut == 529, e
    assert len(appels) == 3 and len(c.attentes) == 2, (len(appels), c.attentes)
    assert all(a <= jev.ATTENTE_REESSAI_MAX_SECONDES for a in c.attentes)

    # Reessais desactives.
    appels.clear()
    async with client(surcharge, max_reessais=0) as c:
        await erreur_de(c.evaluer("s", QUESTIONS))
    assert len(appels) == 1 and c.attentes == []

    # Reseau coupe puis delai depasse : JevIndisponible, sans fuite de detail sensible.
    def coupe(requete):
        raise httpx.ConnectError(f"boom {STATE_SECRET} {CLE}")

    async with client(coupe) as c:
        e = await erreur_de(c.evaluer(STATE_SECRET, QUESTIONS))
    assert isinstance(e, JevIndisponible) and "ConnectError" in str(e), e
    assert CLE not in str(e) and STATE_SECRET not in str(e), "fuite dans le message d'erreur"

    def lent(requete):
        raise httpx.ReadTimeout("trop lent")

    async with client(lent) as c:
        e = await erreur_de(c.evaluer("s", QUESTIONS))
    assert isinstance(e, JevIndisponible) and "ReadTimeout" in str(e)

    # Reseau coupe une fois puis succes.
    etat = {"n": 0}

    def une_coupure(requete):
        etat["n"] += 1
        if etat["n"] == 1:
            raise httpx.ConnectError("coupe")
        return httpx.Response(200, json=REPONSE_OK)

    async with client(une_coupure) as c:
        assert (await c.evaluer("s", QUESTIONS)).choice("action").choix == "a1"


async def verifier_protections_avant_envoi():
    appels = []

    def gestionnaire(requete):
        appels.append(1)
        return httpx.Response(200, json=REPONSE_OK)

    async with client(gestionnaire) as c:
        # 255 options acceptees, 256 refusees avant tout envoi.
        ok = {"action": Choice("q", {f"o{i}": None for i in range(255)})}
        trop = {"action": Choice("q", {f"o{i}": None for i in range(256)})}
        reponse_255 = {"model": "m", "answers": {"action": {"type": "choice", "choice": "o0", "confidence": 1.0,
                                                          "probabilities": {"o0": 1.0}}}}
        async with client(lambda r: httpx.Response(200, json=reponse_255)) as c255:
            assert (await c255.evaluer("s", ok)).choice("action").choix == "o0"
        e = await erreur_de(c.evaluer("s", trop))
        assert "255" in str(e)

        # Score : 2 a 10 niveaux.
        for niveaux in ((), ("un",), tuple(str(i) for i in range(11))):
            await erreur_de(c.evaluer("s", {"x": Score("q", niveaux)}))

        # Choice vide, instructions vides, aucune question, type inconnu, criteres de Noul invalides.
        await erreur_de(c.evaluer("s", {"x": Choice("q", {})}))
        await erreur_de(c.evaluer("s", {"x": Noul("")}))
        await erreur_de(c.evaluer("s", {}))
        await erreur_de(c.evaluer("s", {"x": "pas une question"}))
        await erreur_de(c.evaluer("s", {"x": Noul("q", criteria={"peut-etre": "?"})}))
        await erreur_de(c.evaluer("s", {"": Noul("q")}))

        # State trop long : erreur dediee, avant tout envoi.
        e = await erreur_de(c.evaluer("x" * (jev.LONGUEUR_MAX_STATE_CARACTERES + 1), {"t": Noul("q")}))
        assert isinstance(e, JevEtatTropLong), e
        e = await erreur_de(c.evaluer({"liste": ["x" * (jev.LONGUEUR_MAX_STATE_CARACTERES + 1)]}, {"t": Noul("q")}))
        assert isinstance(e, JevEtatTropLong)

    assert appels == [], "aucune requete ne doit partir quand la validation echoue"

    # Cle vide refusee a la construction.
    for cle in ("", "   ", None):
        try:
            JevClient(cle)
        except JevErreur:
            pass
        else:
            raise AssertionError("une cle vide doit etre refusee")


async def verifier_reponses_invalides():
    def avec(answers):
        return lambda r: httpx.Response(200, json={"model": "m", "answers": answers})

    bonnes = REPONSE_OK["answers"]
    cas = {
        "option inconnue": {**bonnes, "action": {**bonnes["action"], "choice": "supprimer_tout"}},
        "reponse manquante": {k: v for k, v in bonnes.items() if k != "terminee"},
        "mauvais type": {**bonnes, "terminee": {"type": "choice", "choice": "a1", "confidence": 1, "probabilities": {}}},
        "confidence absente": {**bonnes, "action": {k: v for k, v in bonnes["action"].items() if k != "confidence"}},
        "noul hors intervalle": {**bonnes, "terminee": {"type": "noul", "noul": 1.7}},
        "probabilites non numeriques": {**bonnes, "action": {**bonnes["action"], "probabilities": {"a1": "beaucoup"}}},
        "reponse non objet": {**bonnes, "importance": 3},
    }
    for nom, answers in cas.items():
        async with client(avec(answers)) as c:
            e = await erreur_de(c.evaluer("s", QUESTIONS))
        assert not isinstance(e, JevIndisponible), nom

    # Corps non JSON et champ answers absent.
    async with client(lambda r: httpx.Response(200, text="<html>pas du json</html>")) as c:
        await erreur_de(c.evaluer("s", QUESTIONS))
    async with client(lambda r: httpx.Response(200, json={"model": "m"})) as c:
        await erreur_de(c.evaluer("s", QUESTIONS))

    # Usage absent ou etrange : pas d'erreur, compteurs a zero.
    sans_usage = {"model": "m", "answers": bonnes, "usage": {"input_tokens": "beaucoup"}}
    async with client(lambda r: httpx.Response(200, json=sans_usage)) as c:
        r = await c.evaluer("s", QUESTIONS)
    assert (r.tokens_entree, r.tokens_sortie) == (0, 0)


def verifier_environnement():
    anciennes = {k: os.environ.pop(k, None) for k in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "TYPESAFE_MODEL")}
    try:
        assert jev.creer_client_depuis_env() is None, "sans cle : pas de client, pas de crash"
        os.environ["TYPESAFE_API_KEY"] = "   "
        assert jev.creer_client_depuis_env() is None, "cle blanche = absente"
        os.environ["TYPESAFE_API_KEY"] = CLE
        c = jev.creer_client_depuis_env()
        assert isinstance(c, JevClient) and c._model == "jev-1.13.0" and c._url == "https://api.typesafe.ai/v1/systemone"
        os.environ["TYPESAFE_BASE_URL"] = "https://passerelle.exemple/"
        os.environ["TYPESAFE_MODEL"] = "jev-latest"
        c = jev.creer_client_depuis_env()
        assert c._url == "https://passerelle.exemple/v1/systemone" and c._model == "jev-latest"
    finally:
        for cle, valeur in anciennes.items():
            if valeur is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = valeur


async def principal():
    await verifier_requete_et_reponse()
    await verifier_erreurs_http()
    await verifier_protections_avant_envoi()
    await verifier_reponses_invalides()
    verifier_environnement()
    print("OK : client Jev (requete, reponses, erreurs, protections, environnement).")


if __name__ == "__main__":
    asyncio.run(principal())
