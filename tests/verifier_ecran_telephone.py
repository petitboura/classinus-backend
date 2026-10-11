"""Vrais outils MCP du telephone, transport remplace : aucune fausse lecture ni fausse marque."""
import asyncio
import serveur_canal_pc
from core import canal_agent_applicatif as canal
from core import outils_action_agent_telephone as outils

ctx = serveur_canal_pc.ctx

LECTURE = {
    "lignes": [
        {"id": 0, "texte": "Exercice 3", "x": 40, "y": 120, "largeur": 300, "hauteur": 50},
        {"id": 1, "texte": "  Calculer   la limite  ", "x": 40, "y": 200, "largeur": 500, "hauteur": 48},
        {"id": 2, "texte": "   ", "x": 0, "y": 0, "largeur": 10, "hauteur": 10},
        {"id": 3, "texte": "ligne sans position"},
    ],
    "largeur": 1080,
    "hauteur": 2340,
    "ecranLargeur": 1080,
    "ecranHauteur": 2340,
    "horodatage": 1,
}


def remplacer(reponse, vus):
    async def demander(user_id, type_action, parametres, on_statut=None):
        vus.append((user_id, type_action, parametres))
        return reponse
    outils.demander_action_ecran_telephone = demander


async def verifier_message_du_canal():
    """La cle du message est distincte de action_systeme : le relais PC ne se declenche jamais."""
    envoyes = []

    async def diffuser(user_id, message, on_statut=None, on_timeout_log=""):
        envoyes.append(message)
        return {"succes": True}

    original = canal._diffuser_et_attendre
    canal._diffuser_et_attendre = diffuser
    try:
        await canal.demander_action_ecran_telephone("u", "lire_texte", {})
    finally:
        canal._diffuser_et_attendre = original
    message = envoyes[0]
    assert message["action_ecran_telephone"] == "lire_texte" and message["parametres"] == {}
    assert "action_systeme" not in message and message["id"]


async def verifier_lecture():
    vus = []
    remplacer({"succes": True, "lecture": LECTURE}, vus)
    texte = await outils.lire_ecran_telephone(ctx)
    assert vus == [("test-pc", "lire_texte", {})], vus
    assert texte.startswith(outils.AVERTISSEMENT_CONTENU_EXTERIEUR), texte
    assert "2 lignes" in texte and "1080 x 2340" in texte, texte
    assert "0. « Exercice 3 » (zone : gauche 40, haut 120, largeur 300, hauteur 50)" in texte, texte
    assert "1. « Calculer la limite » (zone : gauche 40, haut 200, largeur 500, hauteur 48)" in texte, texte
    assert "ligne sans position" not in texte

    remplacer({"succes": True, "lecture": {**LECTURE, "lignes": []}}, [])
    assert "Aucun texte n'a pu être lu" in await outils.lire_ecran_telephone(ctx)

    anciennes = outils.LONGUEUR_MAX_TEXTE_LECTURE_TELEPHONE
    outils.LONGUEUR_MAX_TEXTE_LECTURE_TELEPHONE = 400
    try:
        longue = [{"id": i, "texte": "mot " * 20, "x": 1, "y": i, "largeur": 5, "hauteur": 5} for i in range(30)]
        remplacer({"succes": True, "lecture": {**LECTURE, "lignes": longue}}, [])
        assert "Lecture coupée" in await outils.lire_ecran_telephone(ctx)
    finally:
        outils.LONGUEUR_MAX_TEXTE_LECTURE_TELEPHONE = anciennes

    remplacer({"succes": False, "code_erreur": "INACTIF"}, [])
    assert "vision de l'écran n'est pas activée" in await outils.lire_ecran_telephone(ctx)
    remplacer({"succes": False, "code_erreur": "LECTURE_ECHEC"}, [])
    assert await outils.lire_ecran_telephone(ctx) == outils.MESSAGE_ERREUR_PAR_DEFAUT
    remplacer(None, [])
    assert await outils.lire_ecran_telephone(ctx) == outils.MESSAGE_ECHEC_TELEPHONE
    remplacer({"succes": True, "lecture": {"lignes": "nimporte quoi"}}, [])
    assert await outils.lire_ecran_telephone(ctx) == outils.MESSAGE_ERREUR_PAR_DEFAUT
    remplacer("pas un dict", [])
    assert await outils.lire_ecran_telephone(ctx) == outils.MESSAGE_ERREUR_PAR_DEFAUT


async def verifier_marque():
    vus = []
    remplacer({"succes": True}, vus)
    texte = await outils.marquer_ecran_telephone(
        "Surligner", 40, 200, 500, 48, ctx, etiquette="  ici  " + "x" * 200, duree_secondes=999
    )
    user_id, type_action, parametres = vus[0]
    assert (user_id, type_action) == ("test-pc", "marquer")
    assert parametres["forme"] == "surligner" and (parametres["x"], parametres["y"]) == (40, 200)
    assert (parametres["largeur"], parametres["hauteur"]) == (500, 48)
    assert parametres["duree_secondes"] == 60 and len(parametres["etiquette"]) == 80
    assert parametres["etiquette"].startswith("ici x"), parametres["etiquette"]
    assert "affichée sur le téléphone pendant 60 secondes" in texte, texte

    vus.clear()
    assert "forme inconnue" in await outils.marquer_ecran_telephone("entourer", 1, 1, 5, 5, ctx)
    assert "largeur et une hauteur positives" in await outils.marquer_ecran_telephone("pointer", 1, 1, 0, 5, ctx)
    assert "nombres entiers" in await outils.marquer_ecran_telephone("pointer", 1.5, 1, 5, 5, ctx)
    assert vus == [], "aucune demande ne doit partir pour une marque invalide"

    for code, attendu in (
        ("PERMISSION_REFUSEE", "n'a pas autorisé l'affichage"),
        ("AUCUNE_LECTURE", "lire_ecran_telephone"),
        ("MARQUES_INVALIDES", "zone à marquer n'est pas valide"),
    ):
        remplacer({"succes": False, "code_erreur": code}, [])
        assert attendu in await outils.marquer_ecran_telephone("pointer", 1, 1, 5, 5, ctx)
    remplacer(None, [])
    assert await outils.marquer_ecran_telephone("pointer", 1, 1, 5, 5, ctx) == outils.MESSAGE_ECHEC_TELEPHONE


async def verifier():
    await verifier_message_du_canal()
    await verifier_lecture()
    await verifier_marque()
    assert "lire_ecran_telephone" in outils.marquer_ecran_telephone.__doc__
    print("OK : lecture et marque du telephone, messages d'erreur par code, aucune fausse reussite.")


if __name__ == "__main__":
    asyncio.run(verifier())
