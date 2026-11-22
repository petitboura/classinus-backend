"""
Travail sur des PDF joints à la conversation (21/11/2026, demande Bourama) :
fusionner plusieurs PDF, couper un PDF en morceaux, tourner des pages, remplir un
formulaire, et lire les tableaux d'un PDF.

Comme core/modification_fichiers_office.py : ce module prend des octets et rend
des octets (ou du texte), sans réseau ni stockage. Le retrait des fichiers
joints, l'envoi des résultats et l'enregistrement dans la bibliothèque sont dans
core/outils_travail_documents.py. Les fichiers d'origine ne sont jamais touchés.

Les numéros de page sont comptés à partir de 1, comme à l'écran. Tout est fait avec
PyMuPDF, déjà dans requirements.txt : aucune dépendance ajoutée.

Limites connues, à dire à l'utilisateur quand elles se présentent :
- un PDF protégé par mot de passe n'est pas ouvert ;
- les tableaux ne sont reconnus que sur les pages à texte natif, pas sur un scan ;
- seuls les formulaires PDF standard (AcroForm) sont remplis, pas les formulaires XFA.
"""

import re

NB_MAX_FICHIERS_FUSION = 20
NB_MAX_MORCEAUX = 20


class ErreurPdf(Exception):
    """Une demande invalide ou un PDF inutilisable. Le message est destiné au modèle."""


def _ouvrir(contenu: bytes, nom: str = "le PDF"):
    import fitz

    try:
        document = fitz.open(stream=contenu, filetype="pdf")
    except Exception:
        raise ErreurPdf(f"{nom} est illisible (fichier abîmé ou ce n'est pas un PDF)") from None
    if document.needs_pass:
        document.close()
        raise ErreurPdf(f"{nom} est protégé par un mot de passe : il ne peut pas être ouvert")
    return document


def _octets(document) -> bytes:
    return document.tobytes(garbage=3, deflate=True)


def lire_plages(texte, total: int) -> list[int]:
    """
    Transforme « 1-3, 5, 8- » en indices de pages (à partir de 0), dans l'ordre demandé.
    « 8- » va jusqu'à la fin, « -3 » vaut les 3 premières pages. Vide : toutes les pages.
    """
    if texte is None or str(texte).strip() == "":
        return list(range(total))
    indices: list[int] = []
    for morceau in re.split(r"[;,]", str(texte)):
        morceau = morceau.strip()
        if not morceau:
            continue
        correspondance = re.fullmatch(r"(\d*)\s*-\s*(\d*)", morceau)
        if correspondance:
            debut = int(correspondance.group(1) or 1)
            fin = int(correspondance.group(2) or total)
        elif morceau.isdigit():
            debut = fin = int(morceau)
        else:
            raise ErreurPdf(f"« {morceau} » n'est pas une plage de pages valide (exemples : 3, 1-4, 7-)")
        if debut < 1 or fin < debut:
            raise ErreurPdf(f"la plage « {morceau} » est invalide")
        if fin > total:
            raise ErreurPdf(f"la plage « {morceau} » dépasse la fin du document ({total} pages)")
        indices.extend(range(debut - 1, fin))
    if not indices:
        raise ErreurPdf("aucune page demandée")
    return indices


def nombre_de_pages(contenu: bytes) -> int:
    document = _ouvrir(contenu)
    try:
        return document.page_count
    finally:
        document.close()


# Fusion

def fusionner(contenus: list[bytes], noms: list[str] | None = None) -> tuple[bytes, int]:
    """Met les PDF bout à bout dans l'ordre donné. Renvoie (octets, nombre total de pages)."""
    if not isinstance(contenus, list) or len(contenus) < 2:
        raise ErreurPdf("il faut au moins deux PDF à fusionner")
    if len(contenus) > NB_MAX_FICHIERS_FUSION:
        raise ErreurPdf(f"{NB_MAX_FICHIERS_FUSION} PDF au plus par fusion")
    import fitz

    resultat = fitz.open()
    try:
        for index, contenu in enumerate(contenus):
            nom = (noms[index] if noms and index < len(noms) else None) or f"Le PDF {index + 1}"
            source = _ouvrir(contenu, nom)
            try:
                resultat.insert_pdf(source)
            finally:
                source.close()
        return _octets(resultat), resultat.page_count
    finally:
        resultat.close()


# Découpage

def calculer_morceaux(total: int, plages=None, pages_par_morceau: int = 0) -> list[tuple[str, list[int]]]:
    """
    Les morceaux à produire : une liste de (libellé, indices de pages). `plages` est une
    liste comme ["1-3", "4-6"] (un morceau par plage) ; sinon `pages_par_morceau` coupe
    régulièrement. L'un ou l'autre est obligatoire.
    """
    morceaux: list[tuple[str, list[int]]] = []
    if plages:
        if not isinstance(plages, list):
            raise ErreurPdf("« plages » doit être une liste, par exemple [\"1-3\", \"4-6\"]")
        for plage in plages:
            indices = lire_plages(plage, total)
            morceaux.append((f"pages {str(plage).strip()}", indices))
    elif pages_par_morceau and int(pages_par_morceau) > 0:
        taille = int(pages_par_morceau)
        for debut in range(0, total, taille):
            fin = min(debut + taille, total)
            morceaux.append((f"pages {debut + 1}-{fin}" if fin - debut > 1 else f"page {debut + 1}", list(range(debut, fin))))
    else:
        raise ErreurPdf("indique `plages` (par exemple [\"1-3\", \"4-6\"]) ou `pages_par_morceau`")
    if len(morceaux) > NB_MAX_MORCEAUX:
        raise ErreurPdf(f"{NB_MAX_MORCEAUX} morceaux au plus par appel, demandes-en moins ou plus grands")
    return morceaux


def extraire_pages(contenu: bytes, indices: list[int]) -> bytes:
    """Un nouveau PDF avec seulement ces pages (indices à partir de 0), dans cet ordre."""
    import fitz

    source = _ouvrir(contenu)
    resultat = fitz.open()
    try:
        for indice in indices:
            resultat.insert_pdf(source, from_page=indice, to_page=indice)
        return _octets(resultat)
    finally:
        resultat.close()
        source.close()


# Rotation

def tourner(contenu: bytes, angle, pages=None) -> tuple[bytes, int]:
    """Tourne des pages (toutes par défaut) de 90, 180 ou 270 degrés dans le sens des aiguilles. Renvoie (octets, pages tournées)."""
    try:
        angle = int(angle)
    except (TypeError, ValueError):
        raise ErreurPdf("l'angle doit être un nombre : 90, 180 ou 270 (ou -90)") from None
    if angle % 90 != 0 or angle % 360 == 0:
        raise ErreurPdf("l'angle doit être un multiple de 90 degrés, différent de 0 (exemples : 90, 180, 270, -90)")
    document = _ouvrir(contenu)
    try:
        indices = sorted(set(lire_plages(pages, document.page_count)))
        for indice in indices:
            page = document[indice]
            page.set_rotation((page.rotation + angle) % 360)
        return _octets(document), len(indices)
    finally:
        document.close()


# Formulaires

def _champs(document) -> list:
    """
    Les champs de formulaire, sous forme (page, champ). La page est gardée avec le champ :
    PyMuPDF détache un champ de sa page dès que celle-ci n'est plus référencée, et
    champ.update() échouerait alors.
    """
    champs = []
    for numero in range(document.page_count):
        page = document[numero]
        for champ in page.widgets() or []:
            champs.append((page, champ))
    return champs


def lister_champs(contenu: bytes) -> list[dict]:
    """Les champs de formulaire du PDF : nom, type, valeur actuelle, choix possibles, page."""
    document = _ouvrir(contenu)
    try:
        resultat = []
        for page, champ in _champs(document):
            if champ.field_type_string == "Signature":
                continue  # une signature ne se remplit pas avec du texte
            resultat.append({
                "nom": champ.field_name,
                "type": champ.field_type_string,
                "valeur": champ.field_value,
                "choix": list(champ.choice_values or []) or None,
                "page": page.number + 1,
            })
        return resultat
    finally:
        document.close()


def remplir_formulaire(contenu: bytes, valeurs: dict) -> tuple[bytes, list[str], list[str]]:
    """
    Remplit des champs par leur nom (la casse est ignorée). Pour une case à cocher, la valeur
    est true ou false ; pour les autres champs, un texte. Renvoie (octets, champs remplis,
    noms demandés mais introuvables).
    """
    if not isinstance(valeurs, dict) or not valeurs:
        raise ErreurPdf("aucune valeur à écrire : « valeurs » doit être un objet {nom du champ: valeur}")
    document = _ouvrir(contenu)
    try:
        champs = _champs(document)
        if not champs:
            raise ErreurPdf(
                "ce PDF n'a aucun champ de formulaire remplissable (document à plat, ou formulaire de type XFA)"
            )
        par_nom = {}
        for _, champ in champs:
            par_nom.setdefault((champ.field_name or "").casefold(), []).append(champ)
        remplis, introuvables = [], []
        for nom, valeur in valeurs.items():
            cibles = par_nom.get(str(nom).casefold())
            if not cibles:
                introuvables.append(str(nom))
                continue
            for champ in cibles:
                if champ.field_type_string == "CheckBox":
                    champ.field_value = champ.on_state() if valeur in (True, "true", "True", "oui", "1", 1) else "Off"
                else:
                    champ.field_value = "" if valeur is None else str(valeur)
                champ.update()
            remplis.append(cibles[0].field_name)
        if not remplis:
            raise ErreurPdf(
                "aucun de ces champs n'existe dans le PDF. Champs disponibles : "
                + ", ".join(sorted({c.field_name for _, c in champs if c.field_name}))
            )
        return _octets(document), remplis, introuvables
    finally:
        document.close()


# Tableaux

def _tableau_markdown(lignes: list[list]) -> str:
    propres = [[(" ".join(str(c).split()) if c is not None else "").replace("|", "/") for c in ligne] for ligne in lignes]
    if not propres:
        return ""
    largeur = max(len(ligne) for ligne in propres)
    propres = [ligne + [""] * (largeur - len(ligne)) for ligne in propres]
    # Une colonne vide sur toutes les lignes est un artefact de détection (double trait de bordure).
    gardees = [j for j in range(largeur) if any(ligne[j] for ligne in propres)]
    if gardees and len(gardees) < largeur:
        propres = [[ligne[j] for j in gardees] for ligne in propres]
        largeur = len(gardees)
    texte = ["| " + " | ".join(propres[0]) + " |", "| " + " | ".join("---" for _ in range(largeur)) + " |"]
    texte.extend("| " + " | ".join(ligne) + " |" for ligne in propres[1:])
    return "\n".join(texte)


def lire_tableaux(contenu: bytes, debut_page: int, fin_page: int, budget_caracteres: int, pages_max: int) -> str:
    """
    Les tableaux des pages demandées, en tableaux Markdown, bornés en pages et en caractères.
    Seules les pages à texte natif sont analysées : un scan n'a pas de tableau reconnaissable.
    """
    document = _ouvrir(contenu)
    try:
        total = document.page_count
        debut = max(1, int(debut_page or 1))
        fin = int(fin_page or 0)
        fin = total if fin <= 0 else min(fin, total)
        if debut > total:
            return f"Ce fichier n'a que {total} pages : la page {debut} n'existe pas."
        if fin < debut:
            return f"L'intervalle est vide : la fin ({fin}) est avant le début ({debut})."

        blocs, utilises, derniere, sans_texte = [], 0, debut - 1, 0
        for numero in range(debut, fin + 1):
            if numero - debut >= pages_max:
                break
            page = document[numero - 1]
            if not page.get_text("text").strip():
                sans_texte += 1
                derniere = numero
                continue
            try:
                tableaux = page.find_tables().tables
            except Exception:
                tableaux = []
            blocs_page = [
                f"--- Page {numero}, tableau {position} ---\n{_tableau_markdown(tableau.extract())}"
                for position, tableau in enumerate(tableaux, start=1)
            ]
            taille_page = sum(len(b) for b in blocs_page)
            if blocs and utilises + taille_page > budget_caracteres:
                break  # la page entière sera lue à l'appel suivant, jamais un tableau coupé en deux
            blocs.extend(b[:budget_caracteres] for b in blocs_page)
            utilises += taille_page
            derniere = numero

        resultat = "\n\n".join(blocs) if blocs else "Aucun tableau reconnu sur ces pages."
        if derniere < fin:
            resultat += (
                f"\n\n[Lecture partielle : pages {debut} à {derniere} sur {total}. "
                f"Rappelle l'outil avec debut_page={derniere + 1} pour la suite.]"
            )
        if sans_texte:
            resultat += (
                f"\n\n[{sans_texte} page(s) sans texte natif (scan ou image) : les tableaux n'y sont pas reconnus. "
                "Lis ces pages avec le mode pages pour obtenir leur texte par reconnaissance de caractères.]"
            )
        return resultat
    finally:
        document.close()
