"""Construction d'un document Word (.docx) à partir d'un texte markdown simple.

Mise en forme prise en charge : titres (# à ####), gras, italique, code en ligne, liens,
listes à puces et numérotées (avec sous-niveaux, chaque liste numérotée repart de 1),
tableaux, citations (>), blocs de code (```), séparateurs (---), page A4, numéros de page.

Tous les réglages visuels sont dans PARAMETRES : aucune valeur n'est écrite dans le code plus bas.
"""
import io
import re

import docx as docx_lib
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt

PARAMETRES = {
    "largeur_page_mm": 210,
    "hauteur_page_mm": 297,
    "marge_cm": 2.5,
    "police": "Calibri",
    "taille_police_pt": 11,
    "espace_apres_pt": 6,
    "police_code": "Consolas",
    "taille_code_pt": 10,
    "retrait_code_cm": 0.5,
    "couleur_entete_tableau": "D9E2F3",
    "couleur_lien": "0563C1",
    "couleur_separateur": "A6A6A6",
    "espace_cellule_pt": 2,
    "espace_apres_tableau_pt": 8,
    "niveau_titre_max": 4,
    "niveau_liste_max": 3,
}

_STYLE_PUCE = {0: "List Bullet", 1: "List Bullet 2", 2: "List Bullet 3"}
_STYLE_NUMERO = {0: "List Number", 1: "List Number 2", 2: "List Number 3"}

_RE_TITRE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_RE_PUCE = re.compile(r"^(\s*)[-*\u2022+]\s+(.*\S)\s*$")
_RE_NUMERO = re.compile(r"^(\s*)\d+[.)]\s+(.*\S)\s*$")
_RE_SEPARATEUR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_RE_LIGNE_TABLEAU = re.compile(r"^\s*\|.*\|\s*$")
_RE_SEPARATEUR_TABLEAU = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_RE_CITATION = re.compile(r"^\s*>\s?(.*)$")
_RE_CODE = re.compile(r"^\s*```")
_RE_NOMBRE = re.compile(r"^[\s+\-]?[\d\s.,%\u20ac$]+$")

_RE_EN_LIGNE = re.compile(
    r"\*\*\*(?P<gi>.+?)\*\*\*"
    r"|\*\*(?P<g>.+?)\*\*"
    r"|__(?P<g2>.+?)__"
    r"|(?<![\w*])\*(?!\s)(?P<i>[^*]+?)(?<!\s)\*(?![\w*])"
    r"|(?<![\w_])_(?!\s)(?P<i2>[^_]+?)(?<!\s)_(?![\w_])"
    r"|`(?P<c>[^`]+)`"
    r"|\[(?P<lt>[^\]]+)\]\((?P<lu>https?://[^)\s]+)\)"
)


def _ajouter_lien(paragraphe, texte: str, url: str) -> None:
    identifiant = paragraphe.part.relate_to(url, RT.HYPERLINK, is_external=True)
    lien = OxmlElement("w:hyperlink")
    lien.set(qn("r:id"), identifiant)
    morceau = OxmlElement("w:r")
    proprietes = OxmlElement("w:rPr")
    couleur = OxmlElement("w:color")
    couleur.set(qn("w:val"), PARAMETRES["couleur_lien"])
    souligne = OxmlElement("w:u")
    souligne.set(qn("w:val"), "single")
    proprietes.append(couleur)
    proprietes.append(souligne)
    morceau.append(proprietes)
    contenu = OxmlElement("w:t")
    contenu.set(qn("xml:space"), "preserve")
    contenu.text = texte
    morceau.append(contenu)
    lien.append(morceau)
    paragraphe._p.append(lien)


def _ajouter_texte(paragraphe, texte: str, gras: bool = False) -> None:
    """Ajoute le texte au paragraphe en traduisant le gras, l'italique, le code et les liens."""
    position = 0
    for trouve in _RE_EN_LIGNE.finditer(texte):
        if trouve.start() > position:
            morceau = paragraphe.add_run(texte[position:trouve.start()])
            morceau.bold = gras or None
        if trouve.group("gi") is not None:
            morceau = paragraphe.add_run(trouve.group("gi"))
            morceau.bold = True
            morceau.italic = True
        elif trouve.group("g") is not None or trouve.group("g2") is not None:
            morceau = paragraphe.add_run(trouve.group("g") or trouve.group("g2"))
            morceau.bold = True
        elif trouve.group("i") is not None or trouve.group("i2") is not None:
            morceau = paragraphe.add_run(trouve.group("i") or trouve.group("i2"))
            morceau.italic = True
            morceau.bold = gras or None
        elif trouve.group("c") is not None:
            morceau = paragraphe.add_run(trouve.group("c"))
            morceau.font.name = PARAMETRES["police_code"]
            morceau.font.size = Pt(PARAMETRES["taille_code_pt"])
        else:
            _ajouter_lien(paragraphe, trouve.group("lt"), trouve.group("lu"))
        position = trouve.end()
    if position < len(texte):
        morceau = paragraphe.add_run(texte[position:])
        morceau.bold = gras or None


def _nouvelle_numerotation(document, nom_style: str) -> int:
    """Crée une numérotation qui repart de 1, basée sur celle du style de liste donné."""
    numerotation = document.part.numbering_part.numbering_definitions._numbering
    id_style = document.styles[nom_style].element.pPr.numPr.numId.val
    id_modele = numerotation.num_having_numId(id_style).abstractNumId.val
    nouvelle = numerotation.add_num(id_modele)
    nouvelle.add_lvlOverride(ilvl=0).add_startOverride(1)
    return nouvelle.numId


def _appliquer_numerotation(paragraphe, identifiant: int) -> None:
    numerotation = paragraphe._p.get_or_add_pPr().get_or_add_numPr()
    numerotation.get_or_add_ilvl().val = 0
    numerotation.get_or_add_numId().val = identifiant


def _niveau_liste(indentation: str, pile: list) -> int:
    """Déduit le niveau d'imbrication d'un élément de liste d'après son indentation."""
    largeur = len(indentation.expandtabs(4))
    while pile and largeur < pile[-1]:
        pile.pop()
    if not pile or largeur > pile[-1]:
        pile.append(largeur)
    return min(len(pile) - 1, PARAMETRES["niveau_liste_max"] - 1)


def _ajouter_separateur(document) -> None:
    paragraphe = document.add_paragraph()
    bordures = OxmlElement("w:pBdr")
    bas = OxmlElement("w:bottom")
    bas.set(qn("w:val"), "single")
    bas.set(qn("w:sz"), "6")
    bas.set(qn("w:space"), "1")
    bas.set(qn("w:color"), PARAMETRES["couleur_separateur"])
    bordures.append(bas)
    paragraphe._p.get_or_add_pPr().append(bordures)


def _decouper_ligne_tableau(ligne: str) -> list:
    contenu = ligne.strip()
    if contenu.startswith("|"):
        contenu = contenu[1:]
    if contenu.endswith("|") and not contenu.endswith("\\|"):
        contenu = contenu[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", contenu)]


def _alignements(ligne_separateur: str, nombre: int) -> list:
    resultat = []
    for cellule in _decouper_ligne_tableau(ligne_separateur):
        debut, fin = cellule.startswith(":"), cellule.endswith(":")
        resultat.append("centre" if debut and fin else "droite" if fin else "gauche" if debut else None)
    return (resultat + [None] * nombre)[:nombre]


def _griser_cellule(cellule, couleur: str) -> None:
    ombre = OxmlElement("w:shd")
    ombre.set(qn("w:val"), "clear")
    ombre.set(qn("w:color"), "auto")
    ombre.set(qn("w:fill"), couleur)
    cellule._tc.get_or_add_tcPr().append(ombre)


def _ajouter_tableau(document, lignes: list) -> None:
    avec_separateur = len(lignes) >= 2 and bool(_RE_SEPARATEUR_TABLEAU.match(lignes[1]))
    lignes_donnees = [_decouper_ligne_tableau(l) for i, l in enumerate(lignes) if not (avec_separateur and i == 1)]
    nombre_colonnes = max(len(l) for l in lignes_donnees)
    alignements = _alignements(lignes[1], nombre_colonnes) if avec_separateur else [None] * nombre_colonnes
    tableau = document.add_table(rows=len(lignes_donnees), cols=nombre_colonnes)
    tableau.style = "Table Grid"
    for numero_ligne, cellules in enumerate(lignes_donnees):
        entete = numero_ligne == 0
        for numero_colonne in range(nombre_colonnes):
            texte = cellules[numero_colonne] if numero_colonne < len(cellules) else ""
            cellule = tableau.cell(numero_ligne, numero_colonne)
            paragraphe = cellule.paragraphs[0]
            paragraphe.paragraph_format.space_after = Pt(PARAMETRES["espace_cellule_pt"])
            _ajouter_texte(paragraphe, texte, gras=entete)
            alignement = alignements[numero_colonne]
            if alignement is None and not entete and _RE_NOMBRE.match(texte or "x"):
                alignement = "droite"
            if alignement == "droite":
                paragraphe.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif alignement == "centre":
                paragraphe.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if entete:
                _griser_cellule(cellule, PARAMETRES["couleur_entete_tableau"])


def _ajouter_numeros_de_page(section) -> None:
    paragraphe = section.footer.paragraphs[0]
    paragraphe.alignment = WD_ALIGN_PARAGRAPH.CENTER
    champ = OxmlElement("w:fldSimple")
    champ.set(qn("w:instr"), "PAGE")
    morceau = OxmlElement("w:r")
    contenu = OxmlElement("w:t")
    contenu.text = "1"
    morceau.append(contenu)
    champ.append(morceau)
    paragraphe._p.append(champ)


def _preparer_document():
    document = docx_lib.Document()
    section = document.sections[0]
    section.page_width = Mm(PARAMETRES["largeur_page_mm"])
    section.page_height = Mm(PARAMETRES["hauteur_page_mm"])
    for cote in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, cote, Cm(PARAMETRES["marge_cm"]))
    normal = document.styles["Normal"]
    normal.font.name = PARAMETRES["police"]
    normal.font.size = Pt(PARAMETRES["taille_police_pt"])
    normal.paragraph_format.space_after = Pt(PARAMETRES["espace_apres_pt"])
    _ajouter_numeros_de_page(section)
    return document


def construire_document_word(titre: str, contenu_markdown: str) -> bytes:
    """Construit le .docx et le renvoie sous forme d'octets."""
    document = _preparer_document()
    if titre:
        document.add_heading(str(titre), level=0)

    lignes = str(contenu_markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    numeros_en_cours: dict = {}
    pile_indentation: list = []
    dernier_etait_tableau = False
    i = 0
    while i < len(lignes):
        ligne = lignes[i]
        if not ligne.strip():
            i += 1
            continue

        est_puce = None if _RE_SEPARATEUR.match(ligne) else _RE_PUCE.match(ligne)
        est_numero = _RE_NUMERO.match(ligne)
        if not (est_puce or est_numero):
            numeros_en_cours.clear()
            pile_indentation.clear()

        espacer = dernier_etait_tableau
        if _RE_CODE.match(ligne):
            i += 1
            while i < len(lignes) and not _RE_CODE.match(lignes[i]):
                paragraphe = document.add_paragraph()
                paragraphe.paragraph_format.space_after = Pt(0)
                paragraphe.paragraph_format.left_indent = Cm(PARAMETRES["retrait_code_cm"])
                if espacer:
                    paragraphe.paragraph_format.space_before = Pt(PARAMETRES["espace_apres_tableau_pt"])
                    espacer = False
                morceau = paragraphe.add_run(lignes[i])
                morceau.font.name = PARAMETRES["police_code"]
                morceau.font.size = Pt(PARAMETRES["taille_code_pt"])
                i += 1
            i += 1
            dernier_etait_tableau = False
            continue

        if _RE_LIGNE_TABLEAU.match(ligne):
            bloc = []
            while i < len(lignes) and _RE_LIGNE_TABLEAU.match(lignes[i]):
                bloc.append(lignes[i])
                i += 1
            if dernier_etait_tableau:
                document.add_paragraph()
            _ajouter_tableau(document, bloc)
            dernier_etait_tableau = True
            continue
        dernier_etait_tableau = False

        titre_trouve = _RE_TITRE.match(ligne)
        if titre_trouve:
            niveau = min(len(titre_trouve.group(1)), PARAMETRES["niveau_titre_max"])
            document.add_heading(titre_trouve.group(2).strip(), level=niveau)
        elif _RE_SEPARATEUR.match(ligne):
            _ajouter_separateur(document)
        elif est_puce:
            niveau = _niveau_liste(est_puce.group(1), pile_indentation)
            paragraphe = document.add_paragraph(style=_STYLE_PUCE[niveau])
            _ajouter_texte(paragraphe, est_puce.group(2))
        elif est_numero:
            niveau = _niveau_liste(est_numero.group(1), pile_indentation)
            for plus_profond in [n for n in numeros_en_cours if n > niveau]:
                del numeros_en_cours[plus_profond]
            if niveau not in numeros_en_cours:
                numeros_en_cours[niveau] = _nouvelle_numerotation(document, _STYLE_NUMERO[niveau])
            paragraphe = document.add_paragraph(style=_STYLE_NUMERO[niveau])
            _appliquer_numerotation(paragraphe, numeros_en_cours[niveau])
            _ajouter_texte(paragraphe, est_numero.group(2))
        elif _RE_CITATION.match(ligne):
            paragraphe = document.add_paragraph(style="Quote")
            _ajouter_texte(paragraphe, _RE_CITATION.match(ligne).group(1).strip())
        else:
            paragraphe = document.add_paragraph()
            _ajouter_texte(paragraphe, ligne.strip())
        if espacer and document.paragraphs:
            dernier = document.paragraphs[-1].paragraph_format
            if dernier.space_before is None:
                dernier.space_before = Pt(PARAMETRES["espace_apres_tableau_pt"])
        i += 1

    flux = io.BytesIO()
    document.save(flux)
    return flux.getvalue()
