"""
Canal en direct : empreinte de l'etat de l'ecran PC (08/10/2026, chantier Jev,
lot 1).

Sert a la detection de boucle (core/detection_boucle_canal.py) : savoir si
l'ecran a change entre deux actions. Deux lectures de l'ecran identiques
donnent la meme empreinte, la moindre difference visible (titre, texte, valeur
d'un champ, etat, position d'un element) en donne une autre.

Decisions de Bourama :
- les coordonnees comptent : un defilement ET une fenetre deplacee sont
  des changements (donc du progres) ;
- l'heure de la barre des taches ne compte pas, sinon l'empreinte changerait
  chaque minute sans vrai progres.

Calculee sur le dictionnaire brut renvoye par l'application PC, AVANT le
formatage en texte (core/outils_action_agent_pc.py, _formater_lecture_ecran),
car ce texte est coupe a une longueur maximale : un changement situe apres la
coupure passerait inapercu.

Module pur : aucun etat, aucun appel reseau, aucun branchement dans le reste
de l'application pour l'instant.
"""

import hashlib
import json
import logging
import os
import re

# Motifs d'un element de la barre des taches qui affiche l'heure ou la date
# (ex. "17:42", "5:42 PM", "08/10/2026"). Reglable sans toucher au code :
# la forme de l'horloge depend de la langue et des reglages de Windows.
MOTIF_HORLOGE_PAR_DEFAUT = r"\b\d{1,2}\s?[:h.]\s?\d{2}\b|\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"


def _compiler_motif_horloge() -> re.Pattern:
    motif = os.environ.get("CLASSINUS_EMPREINTE_HORLOGE_REGEX", MOTIF_HORLOGE_PAR_DEFAUT)
    try:
        return re.compile(motif)
    except re.error as e:
        logging.error(f"Motif d'horloge invalide pour l'empreinte d'ecran, motif par defaut utilise : {e}")
        return re.compile(MOTIF_HORLOGE_PAR_DEFAUT)


_MOTIF_HORLOGE = _compiler_motif_horloge()


def _est_horloge(element: dict) -> bool:
    nom = element.get("nom")
    return isinstance(nom, str) and bool(_MOTIF_HORLOGE.search(nom))


def _element_canonique(element: dict) -> list:
    etats = element.get("etats")
    etats_tries = sorted(e for e in etats if isinstance(e, str)) if isinstance(etats, list) else []
    return [
        element.get("type"),
        element.get("nom"),
        # La valeur d'un champ mot de passe n'est jamais lue : seul le fait
        # qu'elle soit masquee entre dans l'empreinte.
        None if element.get("valeur_masquee") else element.get("valeur"),
        bool(element.get("valeur_masquee")),
        etats_tries,
        element.get("zone"),
        element.get("gauche"),
        element.get("haut"),
        element.get("largeur"),
        element.get("hauteur"),
        element.get("x"),
        element.get("y"),
    ]


def empreinte_lecture_ecran(resultat) -> str | None:
    """
    Empreinte (texte hexadecimal) d'un resultat brut de lecture de l'ecran,
    ou None si le resultat n'est pas exploitable (lecture echouee, absente ou
    en erreur). None veut dire "inconnu", jamais "inchange" : la detection de
    boucle ne conclut rien sur une empreinte inconnue.
    """
    if not isinstance(resultat, dict) or resultat.get("erreur"):
        return None

    zone_lue = resultat.get("zone_lue")
    elements = [e for e in (resultat.get("elements") or []) if isinstance(e, dict)]
    if zone_lue == "barre_des_taches":
        elements = [e for e in elements if not _est_horloge(e)]

    fenetres = [f for f in (resultat.get("fenetres_ouvertes") or []) if isinstance(f, str) and f]
    canonique = {
        "titre": resultat.get("titre_fenetre_active"),
        "application": resultat.get("application"),
        "fenetres": sorted(fenetres),
        "zone": zone_lue,
        "classinus_seul": bool(resultat.get("fenetre_classinus")),
        "menu_ouvert": bool(resultat.get("menu_ouvert")),
        "elements": [_element_canonique(e) for e in elements],
    }
    texte = json.dumps(canonique, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()
