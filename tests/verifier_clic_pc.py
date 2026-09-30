"""Vrai outil MCP, transport remplacé : aucune fausse confirmation de clic."""
import asyncio
import serveur_canal_pc
from core import lecture_ecran_continue
from core import outils_action_agent_pc as outils

# Ce test porte sur le clic, pas sur le verrou de premiere lecture (voir
# verifier_lecture_continue_pc.py) : la lecture est deja faite, et la relecture
# apres le clic est servie par le meme faux transport.
outils.DELAI_APRES_CLIC_SECONDES = 0
lecture_ecran_continue.marquer_lu("test-pc", None)
LECTURE = {"titre_fenetre_active": "Bloc-notes test", "mode": "uia", "fenetre_classinus": False,
           "elements": [{"type": "texte", "nom": "Texte Windows vérifié"}]}


async def verifier():
    for resultat, attendu in (
        ({"ok": True, "curseur_reel_utilise": False}, "sans déplacer"),
        ({"ok": True, "curseur_reel_utilise": True}, "sans demande de validation"),
        ({"ok": False}, "Erreur"),
        ({"ok": True}, "Clic effectué à l'écran"),
        ({"erreur": "Clic incertain"}, "Clic incertain"),
    ):
        async def demander(user_id, action, parametres, on_statut=None, resultat=resultat):
            if action == "lire_ecran":
                return LECTURE
            assert action == "cliquer_ecran"
            assert parametres == {"x": 120, "y": 80}
            return resultat
        outils._demander_action_systeme = demander
        texte = await outils.cliquer_ecran(120, 80, serveur_canal_pc.ctx)
        assert attendu in texte, texte
    assert "ne demande aucune validation" in outils.cliquer_ecran.__doc__
    print("OK : clic indépendant, repli annoncé sans validation et échec sans faux succès.")


if __name__ == "__main__":
    asyncio.run(verifier())
