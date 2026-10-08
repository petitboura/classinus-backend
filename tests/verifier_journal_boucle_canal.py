"""
Journal de tache, empreinte d'ecran et detection de boucle du canal en direct
(08/10/2026, chantier Jev, lot 1).

Aucun reseau, aucun faux transport : les trois modules sont purs ou en memoire.
Verifie :
- empreinte : stable pour une meme lecture, change avec le texte, la valeur d'un
  champ, l'etat, et les coordonnees (defilement, fenetre deplacee) ; l'heure de
  la barre des taches est ignoree ; une lecture inexploitable donne None ;
  un champ masque ne revele jamais sa valeur ;
- journal : ordre, bornes, coupe des textes, isolation par conversation,
  question en attente de reponse, resume compact pour Jev ;
- boucle : repetition, cycle A B A B, aucun faux positif quand l'ecran change,
  empreinte inconnue sans conclusion, escalade puis blocage.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import detection_boucle_canal as boucle
from core import empreinte_ecran
from core import journal_tache_canal as journal
from core.detection_boucle_canal import Verdict
from core.journal_tache_canal import EntreeJournal

LECTURE = {
    "titre_fenetre_active": "Bloc-notes", "application": "notepad", "fenetre_classinus": False,
    "mode": "uia", "fenetres_ouvertes": ["Navigateur", "Explorateur"],
    "elements": [
        {"type": "bouton", "nom": "Enregistrer", "x": 10, "y": 20, "gauche": 0, "haut": 10, "largeur": 20, "hauteur": 20},
        {"type": "champ", "nom": "Texte", "valeur": "bonjour", "etats": ["focus", "editable"], "x": 50, "y": 60},
    ],
}


def copie(lecture, **changements):
    nouvelle = {**lecture, "elements": [dict(e) for e in lecture["elements"]]}
    nouvelle.update(changements)
    return nouvelle


def verifier_empreinte():
    e0 = empreinte_ecran.empreinte_lecture_ecran(LECTURE)
    assert isinstance(e0, str) and len(e0) == 64, e0
    # Meme lecture : meme empreinte, meme si l'ordre des fenetres ou des etats change.
    assert e0 == empreinte_ecran.empreinte_lecture_ecran(copie(LECTURE)), "instable"
    inverse = copie(LECTURE, fenetres_ouvertes=["Explorateur", "Navigateur"])
    inverse["elements"][1]["etats"] = ["editable", "focus"]
    assert e0 == empreinte_ecran.empreinte_lecture_ecran(inverse), "ordre des fenetres ou des etats"

    # Chaque difference visible change l'empreinte.
    texte = copie(LECTURE)
    texte["elements"][1]["valeur"] = "bonjour a tous"
    assert empreinte_ecran.empreinte_lecture_ecran(texte) != e0, "valeur d'un champ"
    etat = copie(LECTURE)
    etat["elements"][1]["etats"] = ["editable"]
    assert empreinte_ecran.empreinte_lecture_ecran(etat) != e0, "etat d'un element"
    titre = copie(LECTURE, titre_fenetre_active="Autre")
    assert empreinte_ecran.empreinte_lecture_ecran(titre) != e0, "titre de fenetre"
    # Decision de Bourama : les coordonnees comptent (defilement, fenetre deplacee).
    defile = copie(LECTURE)
    defile["elements"][0]["y"] = 120
    defile["elements"][0]["haut"] = 110
    assert empreinte_ecran.empreinte_lecture_ecran(defile) != e0, "defilement"
    deplace = copie(LECTURE)
    for element in deplace["elements"]:
        element["x"] += 300
    assert empreinte_ecran.empreinte_lecture_ecran(deplace) != e0, "fenetre deplacee"

    # Lecture inexploitable : None (inconnu), jamais une empreinte "inchangee".
    for mauvais in (None, "texte", [], {"erreur": "echec"}):
        assert empreinte_ecran.empreinte_lecture_ecran(mauvais) is None, mauvais

    # Barre des taches : l'heure est ignoree, pas le reste.
    def barre(heure, bouton="Demarrer"):
        return {
            "zone_lue": "barre_des_taches", "mode": "uia",
            "elements": [{"type": "bouton", "nom": bouton, "x": 5, "y": 5}, {"type": "texte", "nom": heure, "x": 900, "y": 5}],
        }
    assert empreinte_ecran.empreinte_lecture_ecran(barre("17:42")) == empreinte_ecran.empreinte_lecture_ecran(barre("17:43"))
    assert empreinte_ecran.empreinte_lecture_ecran(barre("5:42 PM 08/10/2026")) == empreinte_ecran.empreinte_lecture_ecran(barre("5:43 PM 09/10/2026"))
    assert empreinte_ecran.empreinte_lecture_ecran(barre("17:42")) != empreinte_ecran.empreinte_lecture_ecran(barre("17:42", bouton="Autre"))
    # Hors barre des taches, un texte qui ressemble a une heure compte bien.
    horloge_appli = copie(LECTURE)
    horloge_appli["elements"][0]["nom"] = "Minuteur 12:30"
    horloge_appli2 = copie(LECTURE)
    horloge_appli2["elements"][0]["nom"] = "Minuteur 12:29"
    assert empreinte_ecran.empreinte_lecture_ecran(horloge_appli) != empreinte_ecran.empreinte_lecture_ecran(horloge_appli2)

    # Champ masque : sa valeur n'entre jamais dans l'empreinte.
    secret_a = copie(LECTURE)
    secret_a["elements"][1].update({"valeur": "secret-un", "valeur_masquee": True})
    secret_b = copie(LECTURE)
    secret_b["elements"][1].update({"valeur": "secret-deux", "valeur_masquee": True})
    assert empreinte_ecran.empreinte_lecture_ecran(secret_a) == empreinte_ecran.empreinte_lecture_ecran(secret_b)


def action(auteur, outil, cible, avant, apres=None, reussi=True):
    return EntreeJournal(
        auteur=auteur, genre="action", outil=outil, cible=cible, reussi=reussi,
        empreinte_avant=avant, empreinte_apres=apres if apres is not None else avant,
    )


def verifier_journal():
    u, c = "u-test", "conv-1"
    journal.effacer(u, c)
    assert journal.entrees(u, c) == [] and journal.resume_compact(u, c) == ""

    journal.ajouter(u, c, action("jev", "cliquer_ecran", "Enregistrer", "e1", "e2"))
    journal.ajouter(u, c, EntreeJournal(auteur="jev", genre="parole", texte="Je clique sur Enregistrer"))
    journal.ajouter(u, c, action("grand_modele", "taper_clavier", "champ Texte", "e2", "e3", reussi=False))
    toutes = journal.entrees(u, c)
    assert [e.genre for e in toutes] == ["action", "parole", "action"], toutes
    assert [e.genre for e in journal.entrees(u, c, genre="action")] == ["action", "action"]
    resume = journal.resume_compact(u, c)
    assert "cliquer_ecran sur « Enregistrer », réussi" in resume, resume
    assert "taper_clavier sur « champ Texte », échoué (décidé en escalade)" in resume, resume
    assert "Je clique sur Enregistrer" in resume, resume
    assert "en attente" not in resume

    # Question : Jev ne doit plus agir tant que l'etudiant n'a pas repondu.
    assert journal.question_en_attente(u, c) is False
    journal.ajouter(u, c, EntreeJournal(auteur="grand_modele", genre="question", texte="Quel fichier ouvrir ?"))
    assert journal.question_en_attente(u, c) is True
    assert "ne lance aucune action" in journal.resume_compact(u, c)
    journal.marquer_reponse_recue(u, c)
    assert journal.question_en_attente(u, c) is False
    assert "ne lance aucune action" not in journal.resume_compact(u, c)

    # Resume borne aux N dernieres entrees.
    assert journal.resume_compact(u, c, nb_entrees=1).count("\n") == 0
    assert journal.resume_compact(u, c, nb_entrees=0) == ""

    # Isolation entre conversations et entre utilisateurs.
    assert journal.entrees(u, "conv-2") == [] and journal.entrees("autre", c) == []

    # Coupe des textes longs, bornes du nombre d'entrees.
    journal.effacer(u, c)
    journal.ajouter(u, c, EntreeJournal(auteur="backend", genre="parole", texte="x" * 5000, cible="y" * 5000))
    e = journal.entrees(u, c)[0]
    assert len(e.texte) == journal.LONGUEUR_MAX_TEXTE and e.texte.endswith("…"), len(e.texte)
    assert len(e.cible) == journal.LONGUEUR_MAX_CIBLE
    journal.effacer(u, c)
    for i in range(journal.NB_MAX_ENTREES_PAR_JOURNAL + 10):
        journal.ajouter(u, c, action("jev", "cliquer_ecran", f"cible-{i}", f"e{i}"))
    restantes = journal.entrees(u, c)
    assert len(restantes) == journal.NB_MAX_ENTREES_PAR_JOURNAL, len(restantes)
    assert restantes[-1].cible == f"cible-{journal.NB_MAX_ENTREES_PAR_JOURNAL + 9}"

    # Valeurs inconnues refusees.
    for mauvais in (EntreeJournal(auteur="robot", genre="action"), EntreeJournal(auteur="jev", genre="inconnu")):
        try:
            journal.ajouter(u, c, mauvais)
        except ValueError:
            pass
        else:
            raise AssertionError("auteur ou genre inconnu accepte")

    # Aucun identifiant de conversation : etat partage par utilisateur, sans planter.
    journal.effacer(u, None)
    journal.ajouter(u, None, action("jev", "cliquer_ecran", "A", "e1"))
    assert len(journal.entrees(u, None)) == 1
    journal.effacer(u, None)
    journal.effacer(u, c)


def verifier_boucle():
    jev, grand = "jev", "grand_modele"

    # Rien ou une seule action : pas de boucle.
    assert boucle.analyser([]).verdict == Verdict.AUCUNE
    assert boucle.analyser([action(jev, "cliquer_ecran", "A", "X")]).verdict == Verdict.AUCUNE

    # Repetition : meme action, meme cible, meme ecran. Premier signal : escalade.
    journal_rep = [action(jev, "cliquer_ecran", "Valider", "X"), action(jev, "cliquer_ecran", "Valider", "X")]
    r = boucle.analyser(journal_rep)
    assert (r.verdict, r.motif, r.longueur) == (Verdict.SANS_EFFET, "repetition", 2), r
    # Le grand modele repete apres l'escalade : arret.
    journal_rep.append(action(grand, "cliquer_ecran", "Valider", "X"))
    r = boucle.analyser(journal_rep)
    assert (r.verdict, r.motif, r.longueur) == (Verdict.BLOQUEE, "repetition", 3), r
    # Le grand modele fait autre chose : la boucle est rompue.
    rompue = journal_rep[:2] + [action(grand, "taper_clavier", "champ", "X", "Y")]
    assert boucle.analyser(rompue).verdict == Verdict.AUCUNE

    # Faux positif evite : meme action mais l'ecran a change entre temps.
    suivant = [action(jev, "cliquer_ecran", "Suivant", "E1", "E2"), action(jev, "cliquer_ecran", "Suivant", "E2", "E3"),
               action(jev, "cliquer_ecran", "Suivant", "E3", "E4")]
    assert boucle.analyser(suivant).verdict == Verdict.AUCUNE
    # Meme outil, cible differente : pas une repetition.
    assert boucle.analyser([action(jev, "cliquer_ecran", "A", "X"), action(jev, "cliquer_ecran", "B", "X")]).verdict == Verdict.AUCUNE

    # Empreinte inconnue : aucune conclusion.
    inconnue = [action(jev, "cliquer_ecran", "Valider", None), action(jev, "cliquer_ecran", "Valider", None)]
    inconnue = [EntreeJournal(auteur=e.auteur, genre=e.genre, outil=e.outil, cible=e.cible) for e in inconnue]
    assert boucle.analyser(inconnue).verdict == Verdict.AUCUNE

    # Cycle A B A B avec retour au meme ecran un tour sur deux.
    cycle = [action(jev, "cliquer_ecran", "A", "X"), action(jev, "cliquer_ecran", "B", "Y"),
             action(jev, "cliquer_ecran", "A", "X")]
    assert boucle.analyser(cycle).verdict == Verdict.AUCUNE, "trois actions ne font pas deux motifs"
    cycle.append(action(jev, "cliquer_ecran", "B", "Y"))
    r = boucle.analyser(cycle)
    assert (r.verdict, r.motif, r.longueur) == (Verdict.SANS_EFFET, "cycle", 4), r
    cycle.append(action(grand, "cliquer_ecran", "A", "X"))
    r = boucle.analyser(cycle)
    assert (r.verdict, r.motif, r.longueur) == (Verdict.BLOQUEE, "cycle", 5), r

    # Bouton bascule clique sans cesse : l'ecran alterne X, Y, X, Y, c'est un cycle.
    bascule = [action(jev, "cliquer_ecran", "Mode", "X", "Y"), action(jev, "cliquer_ecran", "Mode", "Y", "X"),
               action(jev, "cliquer_ecran", "Mode", "X", "Y"), action(jev, "cliquer_ecran", "Mode", "Y", "X")]
    assert boucle.analyser(bascule).verdict == Verdict.SANS_EFFET

    # A B A B mais l'ecran progresse a chaque tour : pas une boucle.
    progres = [action(jev, "cliquer_ecran", "A", "E1"), action(jev, "cliquer_ecran", "B", "E2"),
               action(jev, "cliquer_ecran", "A", "E3"), action(jev, "cliquer_ecran", "B", "E4")]
    assert boucle.analyser(progres).verdict == Verdict.AUCUNE

    # Les paroles et questions du journal ne comptent pas comme des actions.
    melange = [action(jev, "cliquer_ecran", "Valider", "X"),
               EntreeJournal(auteur=jev, genre="parole", texte="Je clique"),
               action(jev, "cliquer_ecran", "Valider", "X")]
    assert boucle.analyser(melange).verdict == Verdict.SANS_EFFET

    # Seuil de repetitions reglable ; jamais moins de 2 (une action seule n'est pas une boucle).
    trois = [action(jev, "cliquer_ecran", "V", "X")] * 2
    assert boucle.analyser(trois, repetitions=3).verdict == Verdict.AUCUNE
    assert boucle.analyser(trois[:1] * 2, repetitions=1).verdict == Verdict.SANS_EFFET

    # Bout en bout avec le vrai journal.
    u, c = "u-boucle", "conv-b"
    journal.effacer(u, c)
    for _ in range(2):
        journal.ajouter(u, c, action(jev, "cliquer_ecran", "Valider", "X"))
    assert boucle.analyser(journal.entrees(u, c)).verdict == Verdict.SANS_EFFET
    journal.ajouter(u, c, action(grand, "cliquer_ecran", "Valider", "X"))
    assert boucle.analyser(journal.entrees(u, c)).verdict == Verdict.BLOQUEE
    journal.effacer(u, c)


def verifier():
    verifier_empreinte()
    verifier_journal()
    verifier_boucle()
    print("OK : empreinte d'ecran, journal de tache, detection de boucle.")


if __name__ == "__main__":
    verifier()
