"""Construction d'une présentation PowerPoint (.pptx) lisible à partir d'une liste de diapositives.

Chaque diapositive est un dictionnaire. Clés reconnues (toutes facultatives sauf une au moins) :
    titre     : titre de la diapositive
    contenu   : texte ; les lignes qui commencent par -, *, un point rond ou un numéro deviennent des puces
    puces     : liste de textes, chacun devient une puce
    notes     : notes de l'orateur (non visibles sur la diapositive)
    tableau   : {"en_tetes": [...], "lignes": [[...], ...]}
    graphique : {"type": "colonnes|barres|ligne|camembert", "categories": [...],
                 "series": [{"nom": "...", "valeurs": [...]}]}
Une diapositive qui n'a qu'un titre devient une page de section. Un texte trop long est réparti sur
plusieurs diapositives dont le titre porte la mention (2/3).

Tous les réglages visuels sont dans PARAMETRES : aucune valeur n'est écrite dans le code plus bas.
"""
import io
import logging
import math
import re

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

PARAMETRES = {
    "largeur_po": 13.333,
    "hauteur_po": 7.5,
    "couleur_principale": "1F4E79",
    "couleur_texte": "262626",
    "couleur_secondaire": "7F7F7F",
    "couleur_fond_clair": "FFFFFF",
    "police": "Calibri",
    "marge_po": 0.7,
    "taille_titre_pt": 32,
    "taille_titre_couverture_pt": 44,
    "taille_sous_titre_pt": 22,
    "taille_numero_pt": 12,
    "tailles_corps_pt": [24, 22, 20, 18, 16, 14],
    "interligne_corps": 1.35,
    "facteur_largeur_caractere": 0.5,
    "espace_apres_puce_pt": 8,
    "retrait_puce_po": 0.3,
    "hauteur_titre_po": 1.2,
    "hauteur_barre_po": 0.08,
    "largeur_barre_po": 1.2,
    "hauteur_ligne_tableau_po": 0.45,
    "taille_tableau_pt": 14,
    "taille_graphique_pt": 14,
    "part_texte_avec_visuel": 0.45,
    "diapositives_max": 60,
}

_RE_COULEUR = re.compile(r"^#?([0-9A-Fa-f]{6})$")
_RE_PUCE = re.compile(r"^\s*(?:[-*\u2022+]|\d+[.)])\s+(.*\S)\s*$")

_TYPES_GRAPHIQUE = {
    "colonnes": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "barres": XL_CHART_TYPE.BAR_CLUSTERED,
    "ligne": XL_CHART_TYPE.LINE_MARKERS,
    "camembert": XL_CHART_TYPE.PIE,
}


def _couleur(hexa: str) -> RGBColor:
    return RGBColor.from_string(hexa.upper())


def _couleur_valide(valeur, defaut: str) -> str:
    trouve = _RE_COULEUR.match(str(valeur or "").strip())
    return trouve.group(1).upper() if trouve else defaut


def _texte_propre(valeur) -> str:
    return "" if valeur is None else str(valeur).strip()


def _lignes_de_texte(diapositive: dict) -> list:
    """Rassemble les puces et le contenu texte en une liste de lignes sans symbole de puce."""
    lignes = []
    contenu = _texte_propre(diapositive.get("contenu"))
    for ligne in contenu.replace("\r\n", "\n").split("\n"):
        if not ligne.strip():
            continue
        trouve = _RE_PUCE.match(ligne)
        lignes.append(trouve.group(1) if trouve else ligne.strip())
    puces = diapositive.get("puces")
    if isinstance(puces, (list, tuple)):
        lignes.extend(_texte_propre(p) for p in puces if _texte_propre(p))
    return lignes


def _nombre_de_lignes(lignes: list, taille_pt: int, largeur_po: float) -> int:
    caracteres_par_ligne = max(1, int(largeur_po * 72 / (taille_pt * PARAMETRES["facteur_largeur_caractere"])))
    return sum(max(1, math.ceil(len(l) / caracteres_par_ligne)) for l in lignes)


def _hauteur_necessaire_po(lignes: list, taille_pt: int, largeur_po: float) -> float:
    nombre = _nombre_de_lignes(lignes, taille_pt, largeur_po)
    interligne = taille_pt * PARAMETRES["interligne_corps"] / 72
    return nombre * interligne + len(lignes) * PARAMETRES["espace_apres_puce_pt"] / 72


def _choisir_taille(lignes: list, largeur_po: float, hauteur_po: float):
    """Renvoie la plus grande taille de police qui tient, ou None si même la plus petite déborde."""
    for taille in PARAMETRES["tailles_corps_pt"]:
        if _hauteur_necessaire_po(lignes, taille, largeur_po) <= hauteur_po:
            return taille
    return None


def _repartir_lignes(lignes: list, largeur_po: float, hauteur_po: float) -> list:
    """Découpe les lignes en groupes qui tiennent chacun dans la zone, à la plus petite taille permise."""
    taille_min = PARAMETRES["tailles_corps_pt"][-1]
    groupes, courant = [], []
    for ligne in lignes:
        if courant and _hauteur_necessaire_po(courant + [ligne], taille_min, largeur_po) > hauteur_po:
            groupes.append(courant)
            courant = []
        courant.append(ligne)
    if courant:
        groupes.append(courant)
    return groupes or [[]]


def _style_texte(execution, taille_pt: int, couleur: str, gras: bool = False) -> None:
    execution.font.name = PARAMETRES["police"]
    execution.font.size = Pt(taille_pt)
    execution.font.bold = gras
    execution.font.color.rgb = _couleur(couleur)


def _fond_uni(diapositive, couleur: str) -> None:
    fond = diapositive.background.fill
    fond.solid()
    fond.fore_color.rgb = _couleur(couleur)


def _ajouter_puce(paragraphe, symbole: str = "\u2022") -> None:
    proprietes = paragraphe._p.get_or_add_pPr()
    retrait = Inches(PARAMETRES["retrait_puce_po"])
    proprietes.set("marL", str(int(retrait)))
    proprietes.set("indent", str(-int(retrait)))
    puce = proprietes.makeelement(qn("a:buChar"), {"char": symbole})
    proprietes.append(puce)


def _ajouter_zone_texte(diapositive, gauche, haut, largeur, hauteur):
    boite = diapositive.shapes.add_textbox(gauche, haut, largeur, hauteur)
    cadre = boite.text_frame
    cadre.word_wrap = True
    return boite, cadre


def _ajouter_titre(diapositive, texte: str, couleur_principale: str) -> None:
    marge = Inches(PARAMETRES["marge_po"])
    largeur = Inches(PARAMETRES["largeur_po"] - 2 * PARAMETRES["marge_po"])
    _, cadre = _ajouter_zone_texte(diapositive, marge, Inches(0.35), largeur, Inches(PARAMETRES["hauteur_titre_po"]))
    cadre.vertical_anchor = MSO_ANCHOR.MIDDLE
    execution = cadre.paragraphs[0].add_run()
    execution.text = texte
    _style_texte(execution, PARAMETRES["taille_titre_pt"], couleur_principale, gras=True)
    barre = diapositive.shapes.add_shape(
        1, marge, Inches(0.35 + PARAMETRES["hauteur_titre_po"]),
        Inches(PARAMETRES["largeur_barre_po"]), Inches(PARAMETRES["hauteur_barre_po"]),
    )
    barre.fill.solid()
    barre.fill.fore_color.rgb = _couleur(couleur_principale)
    barre.line.fill.background()


def _ajouter_numero(diapositive, numero: int, total: int) -> None:
    largeur = Inches(1.5)
    gauche = Inches(PARAMETRES["largeur_po"] - PARAMETRES["marge_po"]) - largeur
    haut = Inches(PARAMETRES["hauteur_po"] - 0.55)
    _, cadre = _ajouter_zone_texte(diapositive, gauche, haut, largeur, Inches(0.35))
    paragraphe = cadre.paragraphs[0]
    paragraphe.alignment = PP_ALIGN.RIGHT
    execution = paragraphe.add_run()
    execution.text = f"{numero} / {total}"
    _style_texte(execution, PARAMETRES["taille_numero_pt"], PARAMETRES["couleur_secondaire"])


def _ajouter_puces(diapositive, lignes: list, gauche, haut, largeur_po: float, hauteur_po: float, taille: int) -> None:
    _, cadre = _ajouter_zone_texte(diapositive, gauche, haut, Inches(largeur_po), Inches(hauteur_po))
    for rang, ligne in enumerate(lignes):
        paragraphe = cadre.paragraphs[0] if rang == 0 else cadre.add_paragraph()
        paragraphe.space_after = Pt(PARAMETRES["espace_apres_puce_pt"])
        paragraphe.line_spacing = PARAMETRES["interligne_corps"]
        execution = paragraphe.add_run()
        execution.text = ligne
        _style_texte(execution, taille, PARAMETRES["couleur_texte"])
        _ajouter_puce(paragraphe)


def _ajouter_tableau(diapositive, donnees: dict, gauche, haut, largeur_po: float, couleur_principale: str) -> bool:
    en_tetes = donnees.get("en_tetes")
    lignes = donnees.get("lignes")
    if not isinstance(en_tetes, list) or not en_tetes or not isinstance(lignes, list):
        return False
    colonnes = len(en_tetes)
    toutes = [[_texte_propre(c) for c in en_tetes]]
    for ligne in lignes:
        cellules = [_texte_propre(c) for c in ligne] if isinstance(ligne, (list, tuple)) else [_texte_propre(ligne)]
        toutes.append((cellules + [""] * colonnes)[:colonnes])
    hauteur_ligne = Inches(PARAMETRES["hauteur_ligne_tableau_po"])
    forme = diapositive.shapes.add_table(len(toutes), colonnes, gauche, haut, Inches(largeur_po), hauteur_ligne * len(toutes))
    for numero_ligne, cellules in enumerate(toutes):
        for numero_colonne, texte in enumerate(cellules):
            cellule = forme.table.cell(numero_ligne, numero_colonne)
            cellule.text = ""
            execution = cellule.text_frame.paragraphs[0].add_run()
            execution.text = texte
            entete = numero_ligne == 0
            _style_texte(
                execution, PARAMETRES["taille_tableau_pt"],
                PARAMETRES["couleur_fond_clair"] if entete else PARAMETRES["couleur_texte"], gras=entete,
            )
            if entete:
                cellule.fill.solid()
                cellule.fill.fore_color.rgb = _couleur(couleur_principale)
    return True


def _donnees_graphique(donnees: dict):
    """Valide le graphique demandé. Renvoie (type, données) ou None si les données sont inutilisables."""
    type_graphique = _TYPES_GRAPHIQUE.get(_texte_propre(donnees.get("type")).lower())
    categories = donnees.get("categories")
    series = donnees.get("series")
    if type_graphique is None or not isinstance(categories, list) or not categories or not isinstance(series, list) or not series:
        return None
    jeu = CategoryChartData()
    jeu.categories = [_texte_propre(c) for c in categories]
    for rang, serie in enumerate(series):
        valeurs = serie.get("valeurs") if isinstance(serie, dict) else None
        if not isinstance(valeurs, list) or len(valeurs) != len(categories):
            return None
        try:
            nombres = [float(v) for v in valeurs]
        except (TypeError, ValueError):
            return None
        jeu.add_series(_texte_propre(serie.get("nom")) or str(rang + 1), nombres)
    if type_graphique == XL_CHART_TYPE.PIE and len(series) != 1:
        return None
    return type_graphique, jeu


def _ajouter_graphique(diapositive, donnees: dict, gauche, haut, largeur_po: float, hauteur_po: float) -> bool:
    prepare = _donnees_graphique(donnees)
    if prepare is None:
        return False
    type_graphique, jeu = prepare
    forme = diapositive.shapes.add_chart(type_graphique, gauche, haut, Inches(largeur_po), Inches(hauteur_po), jeu)
    graphique = forme.chart
    graphique.font.size = Pt(PARAMETRES["taille_graphique_pt"])
    graphique.font.name = PARAMETRES["police"]
    graphique.has_legend = len(donnees.get("series")) > 1 or type_graphique == XL_CHART_TYPE.PIE
    if graphique.has_legend:
        graphique.legend.position = XL_LEGEND_POSITION.BOTTOM
        graphique.legend.include_in_layout = False
    return True


def _page_de_couverture(presentation, titre: str, sous_titre: str, couleur_principale: str) -> None:
    diapositive = presentation.slides.add_slide(presentation.slide_layouts[6])
    _fond_uni(diapositive, couleur_principale)
    marge = Inches(PARAMETRES["marge_po"] + 0.3)
    largeur = Inches(PARAMETRES["largeur_po"] - 2 * (PARAMETRES["marge_po"] + 0.3))
    _, cadre = _ajouter_zone_texte(diapositive, marge, Inches(2.3), largeur, Inches(1.8))
    cadre.vertical_anchor = MSO_ANCHOR.BOTTOM
    execution = cadre.paragraphs[0].add_run()
    execution.text = titre
    _style_texte(execution, PARAMETRES["taille_titre_couverture_pt"], PARAMETRES["couleur_fond_clair"], gras=True)
    if sous_titre:
        _, cadre_sous = _ajouter_zone_texte(diapositive, marge, Inches(4.3), largeur, Inches(1.2))
        execution_sous = cadre_sous.paragraphs[0].add_run()
        execution_sous.text = sous_titre
        _style_texte(execution_sous, PARAMETRES["taille_sous_titre_pt"], PARAMETRES["couleur_fond_clair"])


def _page_de_section(presentation, titre: str, couleur_principale: str):
    diapositive = presentation.slides.add_slide(presentation.slide_layouts[6])
    _fond_uni(diapositive, couleur_principale)
    marge = Inches(PARAMETRES["marge_po"] + 0.3)
    largeur = Inches(PARAMETRES["largeur_po"] - 2 * (PARAMETRES["marge_po"] + 0.3))
    _, cadre = _ajouter_zone_texte(diapositive, marge, Inches(2.8), largeur, Inches(1.9))
    cadre.vertical_anchor = MSO_ANCHOR.MIDDLE
    execution = cadre.paragraphs[0].add_run()
    execution.text = titre
    _style_texte(execution, PARAMETRES["taille_titre_couverture_pt"] - 8, PARAMETRES["couleur_fond_clair"], gras=True)
    return diapositive


def _normaliser_diapositives(diapositives) -> list:
    resultat = []
    for element in diapositives if isinstance(diapositives, (list, tuple)) else []:
        if isinstance(element, dict):
            resultat.append(element)
        elif _texte_propre(element):
            resultat.append({"contenu": _texte_propre(element)})
    return resultat[: PARAMETRES["diapositives_max"]]


def construire_presentation(titre: str, diapositives, sous_titre: str = "", couleur_principale: str = ""):
    """Construit le .pptx. Renvoie (octets, avertissements) ; les avertissements sont des phrases pour l'IA."""
    couleur = _couleur_valide(couleur_principale, PARAMETRES["couleur_principale"])
    avertissements: list = []
    sans_numero = {1}
    presentation = Presentation()
    presentation.slide_width = Inches(PARAMETRES["largeur_po"])
    presentation.slide_height = Inches(PARAMETRES["hauteur_po"])
    _page_de_couverture(presentation, _texte_propre(titre), _texte_propre(sous_titre), couleur)

    marge = PARAMETRES["marge_po"]
    largeur_zone = PARAMETRES["largeur_po"] - 2 * marge
    haut_zone = 0.35 + PARAMETRES["hauteur_titre_po"] + PARAMETRES["hauteur_barre_po"] + 0.3
    hauteur_zone = PARAMETRES["hauteur_po"] - haut_zone - 0.7

    for rang, donnees in enumerate(_normaliser_diapositives(diapositives), start=2):
        titre_diapo = _texte_propre(donnees.get("titre"))
        notes = _texte_propre(donnees.get("notes"))
        lignes = _lignes_de_texte(donnees)
        tableau = donnees.get("tableau") if isinstance(donnees.get("tableau"), dict) else None
        graphique = donnees.get("graphique") if isinstance(donnees.get("graphique"), dict) else None

        if titre_diapo and not (lignes or tableau or graphique):
            diapositive = _page_de_section(presentation, titre_diapo, couleur)
            sans_numero.add(len(presentation.slides))
            if notes:
                diapositive.notes_slide.notes_text_frame.text = notes
            continue

        a_visuel = bool(tableau or graphique)
        largeur_texte = largeur_zone * (PARAMETRES["part_texte_avec_visuel"] if (a_visuel and lignes) else 1)
        groupes = _repartir_lignes(lignes, largeur_texte, hauteur_zone)

        taille_commune = min(
            (_choisir_taille(g, largeur_texte, hauteur_zone) or PARAMETRES["tailles_corps_pt"][-1]) for g in groupes
        )
        for numero_groupe, groupe in enumerate(groupes):
            diapositive = presentation.slides.add_slide(presentation.slide_layouts[6])
            _fond_uni(diapositive, PARAMETRES["couleur_fond_clair"])
            suffixe = f" ({numero_groupe + 1}/{len(groupes)})" if len(groupes) > 1 else ""
            _ajouter_titre(diapositive, (titre_diapo + suffixe) if titre_diapo else suffixe.strip(), couleur)
            if groupe:
                _ajouter_puces(diapositive, groupe, Inches(marge), Inches(haut_zone), largeur_texte, hauteur_zone, taille_commune)
            if a_visuel and numero_groupe == 0:
                gauche_visuel = Inches(marge + (largeur_texte + 0.3 if lignes else 0))
                largeur_visuel = largeur_zone - (largeur_texte + 0.3 if lignes else 0)
                if tableau and not _ajouter_tableau(diapositive, tableau, gauche_visuel, Inches(haut_zone), largeur_visuel, couleur):
                    avertissements.append(f"Diapositive {rang} : le tableau est incomplet (en_tetes et lignes sont requis), il n'a pas été ajouté.")
                if graphique and not _ajouter_graphique(diapositive, graphique, gauche_visuel, Inches(haut_zone), largeur_visuel, hauteur_zone):
                    avertissements.append(
                        f"Diapositive {rang} : le graphique n'a pas pu être créé (type colonnes, barres, ligne ou camembert, "
                        "categories et series avec autant de valeurs numériques que de catégories, une seule série pour un camembert)."
                    )
            if notes and numero_groupe == 0:
                diapositive.notes_slide.notes_text_frame.text = notes

    total = len(presentation.slides)
    for numero, diapositive in enumerate(presentation.slides, start=1):
        if numero not in sans_numero:
            _ajouter_numero(diapositive, numero, total)

    flux = io.BytesIO()
    presentation.save(flux)
    for phrase in avertissements:
        logging.warning(phrase)
    return flux.getvalue(), avertissements
