"""
Vérifie la question bloquante du chat (25/11/2026) : lecture de la question, événement de
carte, attente de la réponse (même boucle ET depuis le fil d'un outil, avec sa propre
boucle), réponse d'un autre compte refusée, délai dépassé, bouton Arrêter, réglage du délai.

Lancer : python3 tests/verifier_question_bloquante.py
"""
import asyncio
import os
import sys
import threading
import time
import types

RACINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, RACINE)

from core import canal_agent_applicatif as canal  # noqa: E402
from core import questions_utilisateur as q  # noqa: E402

echecs = []


def verifier(nom, condition, detail=""):
    print(("OK   " if condition else "ECHEC"), nom, detail)
    if not condition:
        echecs.append(nom)


# 1. Lecture de la question
choix = q.lire_question('{"type": "choix_unique", "question": "On attaque par quoi ?", "choix": ["a", "b"]}')
verifier("1a autre ajouté par défaut sur un choix", choix is not None and choix.get("autre") is True)
sans_autre = q.lire_question({"type": "choix_unique", "question": "x", "choix": ["a", "b"], "autre": False})
verifier("1b autre false explicite respecté", sans_autre is not None and sans_autre["autre"] is False)
verifier("1c texte sans autre", "autre" not in (q.lire_question({"type": "texte", "question": "x"}) or {}))
verifier("1d JSON illisible refusé", q.lire_question("pas du json") is None)
verifier("1e sans type refusé", q.lire_question({"question": "x"}) is None)
verifier("1f sans question refusé", q.lire_question({"type": "texte"}) is None)
verifier("1g multi_champs sans question racine accepté si champs", q.lire_question({"type": "multi_champs", "champs": [{"type": "texte", "question": "x"}]}) is not None)
verifier("1h multi_champs sans champs refusé", q.lire_question({"type": "multi_champs", "champs": []}) is None)

# 2. Événement de carte
appel = {"id": "call_1", "name": "poser_question", "arguments": '{"question": "{\\"type\\": \\"oui_non\\", \\"question\\": \\"Ok ?\\"}", "bloquante": true}'}
ev = q.evenement_question_depuis_appel(appel)
verifier("2a événement émis", ev is not None and ev["type"] == "question_en_direct" and ev["id_question"] == "call_1" and ev["bloquante"] is True, str(ev))
verifier("2b question invalide : pas d'événement", q.evenement_question_depuis_appel({"id": "c", "name": "poser_question", "arguments": '{"question": "nop"}'}) is None)
verifier("2c arguments illisibles : pas d'événement", q.evenement_question_depuis_appel({"id": "c", "name": "poser_question", "arguments": "{"}) is None)
verifier("2d bloquante en texte", q.est_bloquante("true") and q.est_bloquante(True) and not q.est_bloquante("false") and not q.est_bloquante(None))


# 3. Attente sur la boucle principale
async def sur_boucle():
    canal._boucle_evenements = None  # appel direct, comme avant
    # 3a réponse du bon compte
    tache = asyncio.ensure_future(canal.attendre_reponse_question("u1", "id1", 5))
    await asyncio.sleep(0.05)
    verifier("3a mauvais compte refusé", canal.repondre_question("u2", "id1", "intrus") is False)
    verifier("3b bon compte accepté", canal.repondre_question("u1", "id1", "ma réponse") is True)
    verifier("3c réponse rendue", await tache == {"reponse": "ma réponse"})
    verifier("3d nettoyage après réponse", "id1" not in canal._attentes and "id1" not in canal._attentes_utilisateur)
    verifier("3e réponse tardive refusée", canal.repondre_question("u1", "id1", "trop tard") is False)
    # 3f délai dépassé
    debut = time.time()
    verifier("3f délai dépassé : None", await canal.attendre_reponse_question("u1", "id2", 0.3) is None)
    verifier("3g durée respectée", 0.25 < time.time() - debut < 1.0, f"{time.time() - debut:.2f}s")
    verifier("3h nettoyage après délai", "id2" not in canal._attentes)
    # 3i bouton Arrêter
    tache = asyncio.ensure_future(canal.attendre_reponse_question("u1", "id3", 5))
    await asyncio.sleep(0.05)
    verifier("3i Arrêter annule 1 attente", canal.annuler_attentes("u1") == 1)
    resultat = await tache
    verifier("3j Arrêter rend l'erreur d'arrêt", isinstance(resultat, dict) and "Arrêt" in resultat.get("erreur", ""), str(resultat))
    # 3k Arrêter d'un autre compte ne touche pas
    tache = asyncio.ensure_future(canal.attendre_reponse_question("u1", "id4", 5))
    await asyncio.sleep(0.05)
    verifier("3k Arrêter d'un autre compte : rien", canal.annuler_attentes("u2") == 0)
    canal.repondre_question("u1", "id4", "ok")
    await tache


asyncio.run(sur_boucle())


# 4. Topologie réelle : l'outil attend depuis un fil avec SA boucle, la réponse arrive sur la boucle principale
boucle_principale = asyncio.new_event_loop()
threading.Thread(target=boucle_principale.run_forever, daemon=True).start()
canal._boucle_evenements = boucle_principale
resultat_fil = {}


def outil_dans_un_fil():
    resultat_fil["valeur"] = asyncio.run(canal.attendre_reponse_question("u1", "id5", 5))


fil = threading.Thread(target=outil_dans_un_fil)
fil.start()
time.sleep(0.4)
verifier("4a attente enregistrée sur la boucle principale", "id5" in canal._attentes)


async def _repondre():
    return canal.repondre_question("u1", "id5", "depuis la page")


verifier("4b réponse acceptée depuis la boucle principale", asyncio.run_coroutine_threadsafe(_repondre(), boucle_principale).result(3) is True)
fil.join(5)
verifier("4c l'outil reçoit la réponse", resultat_fil.get("valeur") == {"reponse": "depuis la page"}, str(resultat_fil))

# 4d Arrêter pendant que l'outil attend depuis son fil
resultat_fil.clear()
fil = threading.Thread(target=outil_dans_un_fil)
fil.start()
time.sleep(0.4)


async def _arreter():
    return canal.annuler_attentes("u1")


# l'identifiant du test précédent est réutilisé : il a bien été nettoyé
verifier("4d Arrêter touche l'attente du fil", asyncio.run_coroutine_threadsafe(_arreter(), boucle_principale).result(3) == 1)
fil.join(5)
verifier("4e l'outil reçoit l'erreur d'arrêt", "Arrêt" in str((resultat_fil.get("valeur") or {}).get("erreur", "")), str(resultat_fil))
boucle_principale.call_soon_threadsafe(boucle_principale.stop)

# 5. Réglage du délai : borné entre le minimum et le maximum, valeur de départ sinon
faux = types.ModuleType("core.mcp_tools")
valeur = {"v": {}}
faux.parametres_outils = lambda: valeur["v"]
sys.modules["core.mcp_tools"] = faux
verifier("5a absent : 600 s", q.delai_question_secondes() == 600)
valeur["v"] = {q.CLE_DELAI_QUESTION: 300}
verifier("5b réglé à 300 s", q.delai_question_secondes() == 300)
valeur["v"] = {q.CLE_DELAI_QUESTION: 5}
verifier("5c plancher 30 s", q.delai_question_secondes() == 30)
valeur["v"] = {q.CLE_DELAI_QUESTION: 99999}
verifier("5d plafond sous la limite Railway (900 s)", q.delai_question_secondes() == q.DELAI_QUESTION_MAX_SECONDES < 900)
valeur["v"] = {q.CLE_DELAI_QUESTION: "abc"}
verifier("5e illisible : 600 s", q.delai_question_secondes() == 600)

print()
print("TOUT EST OK" if not echecs else f"ECHECS : {echecs}")
sys.exit(1 if echecs else 0)
