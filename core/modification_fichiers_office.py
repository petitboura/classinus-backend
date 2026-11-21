"""
Modification d'un fichier Word, Excel ou PowerPoint que l'utilisateur a joint à
la conversation (21/11/2026, demande Bourama : Classinus doit savoir modifier un
fichier envoyé, comme Claude, au lieu d'en recréer un nouveau).

Le fichier d'origine n'est jamais touché. Le modèle donne une LISTE d'opérations
(par exemple remplacer un texte, ajouter une ligne, supprimer une diapositive) ;
ce module les applique une à une sur une copie, en mémoire, puis rend les octets
du nouveau fichier. Si une seule opération échoue, rien n'est rendu : le fichier
n'est jamais livré à moitié modifié.

Ce module ne fait ni réseau ni stockage : il prend des octets et rend des octets.
Le retrait du fichier joint, l'envoi du résultat et l'enregistrement dans la
bibliothèque sont dans core/outils_travail_documents.py.

Les numéros de page, de diapositive, de ligne et de feuille sont comptés à partir
de 1, comme à l'écran.
"""

import copy
import io
import re

FAMILLES_MODIFIABLES = ("docx", "xlsx", "pptx")

# Excel interdit ces caractères dans un nom de feuille (même liste que
# core/generation_documents.py:_nom_feuille_excel, qui, lui, nettoie au lieu de refuser).
_INTERDITS_NOM_FEUILLE = ":\\/?*[]"


class ErreurOperation(Exception):
    """Une opération demandée est invalide ou n'a rien trouvé. Le message est destiné au modèle."""


def _texte_requis(operation: dict, cle: str) -> str:
    valeur = operation.get(cle)
    if not isinstance(valeur, str) or valeur == "":
        raise ErreurOperation(f"le champ « {cle} » est obligatoire (texte non vide)")
    return valeur


def _entier_requis(operation: dict, cle: str, minimum: int = 1) -> int:
    valeur = operation.get(cle)
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        raise ErreurOperation(f"le champ « {cle} » doit être un nombre entier") from None
    if nombre < minimum:
        raise ErreurOperation(f"le champ « {cle} » doit être au moins {minimum}")
    return nombre


def _remplacer_dans_paragraphe(paragraphe, chercher: str, remplacer: str) -> int:
    """
    Remplace `chercher` dans un paragraphe (Word ou PowerPoint, même structure runs).
    Cherche d'abord dans chaque run, ce qui garde toute la mise en forme. Si le texte
    est coupé entre plusieurs runs, le remplacement se fait dans le premier run
    concerné et le reste du texte est retiré des suivants.
    """
    total = 0
    for run in paragraphe.runs:
        if chercher in run.text:
            total += run.text.count(chercher)
            run.text = run.text.replace(chercher, remplacer)
    if total:
        return total

    runs = list(paragraphe.runs)
    if not runs:
        return 0
    texte_complet = "".join(r.text for r in runs)
    position = texte_complet.find(chercher)
    if position < 0:
        return 0
    # Le texte est réparti sur plusieurs runs : on le remet dans le run où il commence.
    total = texte_complet.count(chercher)
    nouveau = texte_complet.replace(chercher, remplacer)
    cumul = 0
    index_depart = 0
    for index, run in enumerate(runs):
        cumul += len(run.text)
        if cumul > position:
            index_depart = index
            break
    # Texte avant le run de départ conservé tel quel, tout le reste va dans ce run.
    avant = "".join(r.text for r in runs[:index_depart])
    runs[index_depart].text = nouveau[len(avant):]
    for run in runs[index_depart + 1:]:
        run.text = ""
    return total


# Word

def _paragraphes_docx(document):
    """Tous les paragraphes : corps, tableaux (même imbriqués), en-têtes et pieds de page."""

    def depuis_tableaux(tableaux):
        for tableau in tableaux:
            for ligne in tableau.rows:
                for cellule in ligne.cells:
                    yield from cellule.paragraphs
                    yield from depuis_tableaux(cellule.tables)

    yield from document.paragraphs
    yield from depuis_tableaux(document.tables)
    for section in document.sections:
        for partie in (section.header, section.footer):
            yield from partie.paragraphs
            yield from depuis_tableaux(partie.tables)


def _trouver_paragraphe_docx(document, contenant: str):
    for paragraphe in document.paragraphs:
        if contenant in paragraphe.text:
            return paragraphe
    raise ErreurOperation(f"aucun paragraphe ne contient « {contenant} »")


def _placer_apres(element_nouveau, document, apres: str | None):
    """Déplace un élément tout juste ajouté en fin de document juste après le paragraphe cité."""
    if apres:
        ancre = _trouver_paragraphe_docx(document, apres)
        ancre._p.addnext(element_nouveau)


def _operation_docx(document, operation: dict) -> str:
    action = operation.get("action")
    if action == "remplacer_texte":
        chercher = _texte_requis(operation, "chercher")
        remplacer = operation.get("remplacer")
        if not isinstance(remplacer, str):
            raise ErreurOperation("le champ « remplacer » est obligatoire (il peut être vide pour effacer)")
        total = sum(_remplacer_dans_paragraphe(p, chercher, remplacer) for p in _paragraphes_docx(document))
        if not total:
            raise ErreurOperation(f"le texte « {chercher} » est introuvable")
        return f"« {chercher} » remplacé {total} fois"

    if action == "ajouter_paragraphe":
        texte = _texte_requis(operation, "texte")
        nouveau = document.add_paragraph(texte)
        _placer_apres(nouveau._p, document, operation.get("apres"))
        return "paragraphe ajouté"

    if action == "ajouter_titre":
        texte = _texte_requis(operation, "texte")
        niveau = int(operation.get("niveau") or 1)
        if niveau not in (1, 2, 3):
            raise ErreurOperation("le champ « niveau » doit valoir 1, 2 ou 3")
        nouveau = document.add_heading(texte, level=niveau)
        _placer_apres(nouveau._p, document, operation.get("apres"))
        return "titre ajouté"

    if action == "supprimer_paragraphe":
        contenant = _texte_requis(operation, "contenant")
        tous = bool(operation.get("tous"))
        a_retirer = [p for p in document.paragraphs if contenant in p.text]
        if not a_retirer:
            raise ErreurOperation(f"aucun paragraphe ne contient « {contenant} »")
        if not tous:
            a_retirer = a_retirer[:1]
        for paragraphe in a_retirer:
            paragraphe._p.getparent().remove(paragraphe._p)
        return f"{len(a_retirer)} paragraphe(s) supprimé(s)"

    if action == "ajouter_tableau":
        en_tetes = operation.get("en_tetes")
        lignes = operation.get("lignes") or []
        if not isinstance(en_tetes, list) or not en_tetes:
            raise ErreurOperation("le champ « en_tetes » doit être une liste non vide")
        if not isinstance(lignes, list):
            raise ErreurOperation("le champ « lignes » doit être une liste de listes")
        tableau = document.add_table(rows=1, cols=len(en_tetes))
        try:
            tableau.style = "Table Grid"
        except Exception:
            pass  # le style n'existe pas dans ce document : le tableau reste sans bordures
        for index, texte in enumerate(en_tetes):
            tableau.rows[0].cells[index].text = str(texte)
        for ligne in lignes:
            cellules = tableau.add_row().cells
            for index, valeur in enumerate(list(ligne)[: len(en_tetes)]):
                cellules[index].text = "" if valeur is None else str(valeur)
        apres = operation.get("apres")
        if apres:
            _trouver_paragraphe_docx(document, apres)._p.addnext(tableau._tbl)
        return "tableau ajouté"

    raise ErreurOperation(
        f"action inconnue « {action} ». Actions Word : remplacer_texte, ajouter_paragraphe, "
        "ajouter_titre, supprimer_paragraphe, ajouter_tableau"
    )


# Excel

def _feuille_xlsx(classeur, operation: dict):
    nom = operation.get("feuille")
    if nom in (None, ""):
        return classeur.active
    if nom not in classeur.sheetnames:
        raise ErreurOperation(f"la feuille « {nom} » n'existe pas (feuilles : {', '.join(classeur.sheetnames)})")
    return classeur[nom]


def _verifier_nom_feuille(nom) -> str:
    if not isinstance(nom, str) or not nom.strip():
        raise ErreurOperation("le nom de feuille est obligatoire")
    nom = nom.strip()
    if len(nom) > 31:
        raise ErreurOperation("un nom de feuille Excel fait 31 caractères au plus")
    if any(c in _INTERDITS_NOM_FEUILLE for c in nom) or nom.startswith("'") or nom.endswith("'"):
        raise ErreurOperation("un nom de feuille Excel ne peut pas contenir : \\ / ? * [ ] ni commencer ou finir par une apostrophe")
    return nom


def _operation_xlsx(classeur, operation: dict) -> str:
    action = operation.get("action")

    if action == "definir_cellule":
        feuille = _feuille_xlsx(classeur, operation)
        cellule = _texte_requis(operation, "cellule").strip().upper()
        if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]*", cellule):
            raise ErreurOperation(f"« {cellule} » n'est pas une adresse de cellule valide (exemple : B3)")
        if "valeur" not in operation:
            raise ErreurOperation("le champ « valeur » est obligatoire (il peut être vide pour effacer)")
        feuille[cellule] = operation["valeur"]  # une valeur qui commence par = reste une formule
        return f"cellule {cellule} modifiée"

    if action == "ajouter_ligne":
        feuille = _feuille_xlsx(classeur, operation)
        valeurs = operation.get("valeurs")
        if not isinstance(valeurs, list) or not valeurs:
            raise ErreurOperation("le champ « valeurs » doit être une liste non vide")
        feuille.append(valeurs)
        return f"ligne {feuille.max_row} ajoutée"

    if action == "ajouter_colonne":
        feuille = _feuille_xlsx(classeur, operation)
        en_tete = _texte_requis(operation, "en_tete")
        valeurs = operation.get("valeurs") or []
        if not isinstance(valeurs, list):
            raise ErreurOperation("le champ « valeurs » doit être une liste")
        colonne = feuille.max_column + 1
        feuille.cell(row=1, column=colonne, value=en_tete)
        for index, valeur in enumerate(valeurs):
            feuille.cell(row=index + 2, column=colonne, value=valeur)
        return f"colonne « {en_tete} » ajoutée"

    if action == "supprimer_ligne":
        feuille = _feuille_xlsx(classeur, operation)
        numero = _entier_requis(operation, "numero")
        if numero > feuille.max_row:
            raise ErreurOperation(f"la feuille n'a que {feuille.max_row} lignes")
        feuille.delete_rows(numero)
        return f"ligne {numero} supprimée"

    if action == "ajouter_feuille":
        nom = _verifier_nom_feuille(operation.get("nom"))
        if nom in classeur.sheetnames:
            raise ErreurOperation(f"la feuille « {nom} » existe déjà")
        classeur.create_sheet(nom)
        return f"feuille « {nom} » ajoutée"

    if action == "renommer_feuille":
        feuille = _feuille_xlsx(classeur, operation)
        nouveau = _verifier_nom_feuille(operation.get("nouveau_nom"))
        if nouveau in classeur.sheetnames and nouveau != feuille.title:
            raise ErreurOperation(f"la feuille « {nouveau} » existe déjà")
        ancien = feuille.title
        feuille.title = nouveau
        return f"feuille « {ancien} » renommée « {nouveau} »"

    raise ErreurOperation(
        f"action inconnue « {action} ». Actions Excel : definir_cellule, ajouter_ligne, ajouter_colonne, "
        "supprimer_ligne, ajouter_feuille, renommer_feuille"
    )


# PowerPoint

def _paragraphes_pptx(formes):
    for forme in formes:
        if getattr(forme, "has_text_frame", False) and forme.has_text_frame:
            yield from forme.text_frame.paragraphs
        if getattr(forme, "has_table", False) and forme.has_table:
            for ligne in forme.table.rows:
                for cellule in ligne.cells:
                    yield from cellule.text_frame.paragraphs
        if getattr(forme, "shape_type", None) == 6:  # groupe de formes
            yield from _paragraphes_pptx(forme.shapes)


def _diapositive_pptx(presentation, operation: dict, cle: str = "numero"):
    numero = _entier_requis(operation, cle)
    diapositives = list(presentation.slides)
    if numero > len(diapositives):
        raise ErreurOperation(f"la présentation n'a que {len(diapositives)} diapositives")
    return numero, diapositives[numero - 1]


def _layout_titre_et_contenu(presentation):
    """Une mise en page du fichier lui-même avec un titre et une zone de texte, sinon la première."""
    for layout in presentation.slide_layouts:
        indices = {p.placeholder_format.idx for p in layout.placeholders}
        if 0 in indices and 1 in indices:
            return layout
    return presentation.slide_layouts[0]


def _operation_pptx(presentation, operation: dict) -> str:
    action = operation.get("action")

    if action == "remplacer_texte":
        chercher = _texte_requis(operation, "chercher")
        remplacer = operation.get("remplacer")
        if not isinstance(remplacer, str):
            raise ErreurOperation("le champ « remplacer » est obligatoire (il peut être vide pour effacer)")
        total = 0
        for diapositive in presentation.slides:
            for paragraphe in _paragraphes_pptx(diapositive.shapes):
                total += _remplacer_dans_paragraphe(paragraphe, chercher, remplacer)
        if not total:
            raise ErreurOperation(f"le texte « {chercher} » est introuvable")
        return f"« {chercher} » remplacé {total} fois"

    if action == "ajouter_diapositive":
        titre = _texte_requis(operation, "titre")
        contenu = operation.get("contenu") or ""
        diapositive = presentation.slides.add_slide(_layout_titre_et_contenu(presentation))
        if diapositive.shapes.title is not None:
            diapositive.shapes.title.text = titre
        zones = [p for p in diapositive.placeholders if p.placeholder_format.idx == 1]
        if contenu and zones:
            zones[0].text_frame.text = contenu
        position = operation.get("position")
        if position not in (None, ""):
            position = _entier_requis(operation, "position")
            liste = presentation.slides._sldIdLst
            elements = list(liste)
            nouvel_element = elements[-1]
            liste.remove(nouvel_element)
            liste.insert(min(position - 1, len(elements) - 1), nouvel_element)
        return f"diapositive « {titre} » ajoutée"

    if action == "supprimer_diapositive":
        numero, _ = _diapositive_pptx(presentation, operation)
        liste = presentation.slides._sldIdLst
        element = list(liste)[numero - 1]
        presentation.part.drop_rel(element.rId)
        liste.remove(element)
        return f"diapositive {numero} supprimée"

    if action == "modifier_notes":
        numero, diapositive = _diapositive_pptx(presentation, operation)
        texte = operation.get("texte")
        if not isinstance(texte, str):
            raise ErreurOperation("le champ « texte » est obligatoire (il peut être vide pour effacer)")
        diapositive.notes_slide.notes_text_frame.text = texte
        return f"notes de la diapositive {numero} modifiées"

    raise ErreurOperation(
        f"action inconnue « {action} ». Actions PowerPoint : remplacer_texte, ajouter_diapositive, "
        "supprimer_diapositive, modifier_notes"
    )


def modifier_fichier_office(famille: str, contenu: bytes, operations: list) -> tuple[bytes, list[str]]:
    """
    Applique les opérations dans l'ordre sur une copie du fichier. Renvoie
    (octets du nouveau fichier, un compte rendu par opération). Lève ErreurOperation,
    avec le numéro de l'opération en cause, à la première qui échoue : le
    fichier n'est alors pas rendu.
    """
    if famille not in FAMILLES_MODIFIABLES:
        raise ErreurOperation("seuls les fichiers Word (.docx), Excel (.xlsx) et PowerPoint (.pptx) sont modifiables")
    if not isinstance(operations, list) or not operations:
        raise ErreurOperation("la liste des opérations est vide")
    if len(operations) > 200:
        raise ErreurOperation("200 opérations au plus par appel")

    if famille == "docx":
        import docx

        objet = docx.Document(io.BytesIO(contenu))
        appliquer = _operation_docx
    elif famille == "xlsx":
        import openpyxl

        objet = openpyxl.load_workbook(io.BytesIO(contenu))  # les formules existantes sont gardées
        appliquer = _operation_xlsx
    else:
        from pptx import Presentation

        objet = Presentation(io.BytesIO(contenu))
        appliquer = _operation_pptx

    comptes_rendus = []
    for numero, operation in enumerate(operations, start=1):
        if not isinstance(operation, dict):
            raise ErreurOperation(f"opération {numero} : chaque opération doit être un objet avec un champ « action »")
        try:
            comptes_rendus.append(appliquer(objet, copy.copy(operation)))
        except ErreurOperation as e:
            raise ErreurOperation(f"opération {numero} : {e}") from None

    tampon = io.BytesIO()
    objet.save(tampon)
    return tampon.getvalue(), comptes_rendus
