"""Verifie que Classinus est toujours informee de la fenetre reellement devant l'etudiant, meme quand elle
lit une autre fenetre par son titre ou le bureau (17/10/2026, demande de Bourama)."""
import serveur_canal_pc  # noqa: F401  (installe les remplacements de test avant l'import des outils)
from core import outils_action_agent_pc as outils

BASE = {"application": None, "fenetre_classinus": False, "coupe": False, "mode": "uia"}
ICONES = [{"type": "élément de liste", "nom": "Corbeille", "x": 40, "y": 50, "gauche": 10, "haut": 20, "largeur": 60, "hauteur": 60, "zone": "bureau"}]


def tester():
    # 1. Fenetre lue derriere : la fenetre devant est donnee en plus.
    derriere = {**BASE, "titre_fenetre_active": "Terminal", "application": "wt", "fenetre_visee": True,
                "fenetres_ouvertes": ["Sans titre - Bloc-notes"], "zone_lue": "fenetre", "elements": [],
                "fenetre_premier_plan": "Sans titre - Bloc-notes"}
    texte = outils._formater_lecture_ecran(derriere)
    assert "Au premier plan, devant l'étudiant : « Sans titre - Bloc-notes »" in texte, texte
    assert "sans être mise devant" in texte

    # 2. Bureau lu pendant qu'une fenetre est devant (titre vide) : la fenetre devant est donnee.
    bureau_demande = {**BASE, "titre_fenetre_active": None, "fenetres_ouvertes": ["Navigateur"], "zone_lue": "bureau",
                      "elements": ICONES, "fenetre_premier_plan": "Sans titre - Bloc-notes"}
    texte = outils._formater_lecture_ecran(bureau_demande)
    assert "Au premier plan, devant l'étudiant : « Sans titre - Bloc-notes »" in texte, texte
    assert "Corbeille" in texte

    # 3. Fenetre normale au premier plan : aucune ligne en double.
    normale = {**BASE, "titre_fenetre_active": "Sans titre - Bloc-notes", "fenetres_ouvertes": [], "zone_lue": "fenetre",
               "elements": [], "fenetre_premier_plan": "Sans titre - Bloc-notes"}
    texte = outils._formater_lecture_ecran(normale)
    assert texte.count("Sans titre - Bloc-notes") == 1 + 0 or "Au premier plan, devant" not in texte, texte

    # 4. Le bureau est devant : la phrase du bureau suffit, pas de doublon.
    devant = {**BASE, "titre_fenetre_active": None, "fenetres_ouvertes": [], "zone_lue": "bureau", "bureau_premier_plan": True,
              "elements": ICONES, "fenetre_premier_plan": "Bureau"}
    texte = outils._formater_lecture_ecran(devant)
    assert "Au premier plan, devant l'étudiant : le bureau" not in texte, texte
    assert "Le bureau de Windows est au premier plan" in texte

    # 5. Ancienne application PC (champ absent) : rien ne change.
    ancien = {**derriere}
    ancien.pop("fenetre_premier_plan")
    assert "Au premier plan, devant" not in outils._formater_lecture_ecran(ancien)
    print("ok : fenetre reellement devant donnee a l'IA")


if __name__ == "__main__":
    tester()
