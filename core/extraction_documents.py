"""
Extraction de texte de tous les fichiers joints en conversation (PDF, Word,
Excel, PowerPoint, anciens formats Office, texte et code, et tout fichier
dont le contenu se lit comme du texte), via lire_fichier() en fin de
module. Les fichiers réellement illisibles (binaires inconnus) ne sont pas
refusés : ils sont acceptés et stockés, seul leur contenu n'est pas lu.

Extraction de texte PDF/Word/Excel, partagée entre l'upload de document
seul en conversation (api/uploads.py:uploader_document_chat) et le
dézipage d'une archive en conversation (core/zip_chat.py, 26/09/2026).

Extrait de api/uploads.py (où ces fonctions vivaient depuis le
2026-07) pour éviter que core/zip_chat.py doive importer depuis api/
(sens de dépendance inversé, risque de dépendance circulaire puisque
api/uploads.py appelle aussi core/zip_chat.py pour démarrer le
dézipage). uploader_document_chat importe désormais tout ceci d'ici au
lieu de le définir localement -- comportement inchangé.
"""

TYPES_DOCUMENTS_AUTORISES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}
TAILLE_MAX_DOCUMENT_OCTETS = 15 * 1024 * 1024  # 15 Mo
LONGUEUR_MAX_TEXTE_EXTRAIT = 30_000  # caractères, pour ne pas saturer le prompt système


def extraire_texte_pdf(contenu_bytes):
    """
    Extraction texte par page + OCR de secours pour les pages scannées
    (26/09, plan validé avec Bourama, voir core/ocr_pages_scannees.py).
    Une page sans texte natif est rendue en image puis passée à
    Tesseract, avec Gemini vision en filet de sécurité si Tesseract
    échoue ou est trop pauvre. Reporté ici depuis api/uploads.py au
    passage du chantier zip (même jour) -- comportement inchangé.
    """
    import io
    import os
    import tempfile

    import PyPDF2

    from core.ocr_pages_scannees import extraire_texte_page_scannee

    reader = PyPDF2.PdfReader(io.BytesIO(contenu_bytes))
    pages_texte = [(page.extract_text() or "").strip() for page in reader.pages]
    numeros_pages_vides = [i for i, texte in enumerate(pages_texte) if not texte]

    if numeros_pages_vides:
        chemin_temp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(contenu_bytes)
                chemin_temp = tmp.name
            for numero in numeros_pages_vides:
                texte_ocr = extraire_texte_page_scannee(chemin_temp, numero)
                if texte_ocr:
                    pages_texte[numero] = texte_ocr
        finally:
            if chemin_temp:
                try:
                    os.remove(chemin_temp)
                except OSError:
                    pass

    return "\n".join(pages_texte)


def extraire_texte_docx(contenu_bytes):
    import io
    import docx

    document = docx.Document(io.BytesIO(contenu_bytes))
    morceaux = [p.text for p in document.paragraphs]

    for table in document.tables:
        for ligne in table.rows:
            morceaux.append("\t".join(cellule.text for cellule in ligne.cells))

    return "\n".join(morceaux)


def extraire_texte_xlsx(contenu_bytes):
    import io
    import openpyxl

    classeur = openpyxl.load_workbook(io.BytesIO(contenu_bytes), data_only=True)
    morceaux = []
    for feuille in classeur.worksheets:
        morceaux.append(f"--- Feuille : {feuille.title} ---")
        for ligne in feuille.iter_rows(values_only=True):
            morceaux.append(
                "\t".join("" if v is None else str(v) for v in ligne)
            )
    return "\n".join(morceaux)


def extraire_texte_par_type_mime(contenu_bytes, type_mime):
    """Point d'entrée générique : renvoie le texte extrait, ou None si
    type_mime n'est pas un des 3 formats gérés ici (voir
    core/zip_chat.py pour le repli texte brut sur les autres types)."""
    extension = TYPES_DOCUMENTS_AUTORISES.get(type_mime)
    if extension == "pdf":
        return extraire_texte_pdf(contenu_bytes)
    if extension == "docx":
        return extraire_texte_docx(contenu_bytes)
    if extension == "xlsx":
        return extraire_texte_xlsx(contenu_bytes)
    return None


TYPE_MIME_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# Formats Office anciens ou voisins : pas de lecteur Python dédié, on les
# convertit en PDF via CloudConvert (si configuré, voir core/conversion_pdf.py)
# puis on extrait le texte du PDF.
EXTENSIONS_OFFICE_ANCIEN = {"doc", "xls", "ppt", "rtf", "odt", "ods", "odp"}

# Formats Office pour lesquels un aperçu PDF a du sens dans le chat. Un
# fichier texte ou du code n'en a pas besoin (et ne doit pas consommer le
# quota de conversion).
EXTENSIONS_AVEC_APERCU = {"docx", "xlsx", "pptx"} | EXTENSIONS_OFFICE_ANCIEN

EXTENSIONS_TEXTE = {
    "txt", "md", "markdown", "csv", "tsv", "json", "jsonl", "yml", "yaml", "xml",
    "html", "htm", "css", "scss", "less", "svg", "tex", "bib", "log", "ini", "toml",
    "cfg", "conf", "env", "srt", "vtt", "rst", "org",
    "py", "ipynb", "js", "jsx", "mjs", "ts", "tsx", "vue", "svelte", "sql",
    "sh", "bash", "zsh", "bat", "ps1", "java", "kt", "swift", "c", "h", "cpp", "hpp",
    "cs", "go", "rs", "rb", "php", "pl", "r", "m", "lua", "dart", "scala", "gradle",
}

TYPES_MIME_TEXTE = {
    "application/json", "application/xml", "application/x-yaml", "application/yaml",
    "application/javascript", "application/x-sh", "application/sql", "application/x-tex",
}


def extension_fichier(nom_fichier):
    nom = nom_fichier or ""
    return nom.rsplit(".", 1)[-1].lower() if "." in nom else ""


def type_document(nom_fichier, type_mime):
    """Famille de traitement d'un fichier joint : pdf, docx, xlsx, pptx,
    office_ancien, texte ou inconnu. L'extension passe avant le type MIME,
    que le navigateur rapporte souvent de travers (octet-stream, vide)."""
    extension = extension_fichier(nom_fichier)
    mime = (type_mime or "").strip().lower()
    if extension == "pdf" or mime == "application/pdf":
        return "pdf"
    if extension == "docx" or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return "docx"
    if extension == "xlsx" or mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return "xlsx"
    if extension == "pptx" or mime == TYPE_MIME_PPTX:
        return "pptx"
    if extension in EXTENSIONS_OFFICE_ANCIEN:
        return "office_ancien"
    if extension in EXTENSIONS_TEXTE or mime.startswith("text/") or mime in TYPES_MIME_TEXTE:
        return "texte"
    return "inconnu"


def decoder_texte(contenu_bytes):
    """Décode un contenu en texte, ou renvoie None s'il est binaire. Jamais
    d'échec sur un encodage : UTF-8 d'abord, puis Windows-1252, puis
    Latin-1 en dernier recours (qui accepte tous les octets)."""
    if contenu_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return contenu_bytes.decode("utf-16", errors="replace")
    if b"\x00" in contenu_bytes[:8192]:
        return None
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            return contenu_bytes.decode(encodage)
        except UnicodeDecodeError:
            continue
    return contenu_bytes.decode("latin-1")


def _ressemble_a_du_texte(texte):
    """Garde-fou pour un fichier d'extension inconnue : lisible seulement si
    presque tous les caractères sont imprimables."""
    if not texte.strip():
        return False
    echantillon = texte[:20000]
    imprimables = sum(1 for c in echantillon if c.isprintable() or c in "\n\r\t")
    return imprimables / len(echantillon) >= 0.95


def _textes_formes_pptx(formes):
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    morceaux = []
    for forme in formes:
        if forme.shape_type == MSO_SHAPE_TYPE.GROUP:
            morceaux.extend(_textes_formes_pptx(forme.shapes))
            continue
        if forme.has_text_frame and forme.text_frame.text.strip():
            morceaux.append(forme.text_frame.text)
        if getattr(forme, "has_table", False) and forme.has_table:
            for ligne in forme.table.rows:
                morceaux.append("\t".join(cellule.text for cellule in ligne.cells))
    return morceaux


def extraire_texte_pptx(contenu_bytes):
    import io
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(contenu_bytes))
    morceaux = []
    for numero, diapositive in enumerate(presentation.slides, start=1):
        morceaux.append(f"--- Diapositive {numero} ---")
        morceaux.extend(_textes_formes_pptx(diapositive.shapes))
        if diapositive.has_notes_slide:
            notes = diapositive.notes_slide.notes_text_frame.text
            if notes.strip():
                morceaux.append(f"Notes : {notes}")
    return "\n".join(morceaux)


def extraire_texte_office_ancien(contenu_bytes, nom_fichier):
    """Texte d'un ancien format Office via conversion PDF. None si la
    conversion n'est pas configurée (CLOUDCONVERT_API_KEY absente)."""
    try:
        from conversion_pdf import conversion_disponible, convertir_en_pdf
    except ImportError:
        from core.conversion_pdf import conversion_disponible, convertir_en_pdf

    if not conversion_disponible():
        return None
    return extraire_texte_pdf(convertir_en_pdf(contenu_bytes, nom_fichier or "document"))


def lire_fichier(nom_fichier, contenu_bytes, type_mime):
    """Point d'entrée unique de lecture d'un fichier joint, quel que soit
    son format. Renvoie {"texte", "tronque", "raison"} :
    - texte lu et raison None en cas de succès ;
    - texte None et raison donnée sinon : TYPE_NON_PRIS_EN_CHARGE (binaire
      inconnu), CONVERSION_INDISPONIBLE (ancien format Office sans clé de
      conversion), AUCUN_TEXTE_TROUVE (fichier lisible mais vide, ou scan
      sans texte), ECHEC_EXTRACTION (erreur pendant la lecture)."""
    famille = type_document(nom_fichier, type_mime)
    try:
        if famille == "pdf":
            texte = extraire_texte_pdf(contenu_bytes)
        elif famille == "docx":
            texte = extraire_texte_docx(contenu_bytes)
        elif famille == "xlsx":
            texte = extraire_texte_xlsx(contenu_bytes)
        elif famille == "pptx":
            texte = extraire_texte_pptx(contenu_bytes)
        elif famille == "office_ancien":
            texte = extraire_texte_office_ancien(contenu_bytes, nom_fichier)
            if texte is None:
                return {"texte": None, "tronque": False, "raison": "CONVERSION_INDISPONIBLE"}
        else:
            texte = decoder_texte(contenu_bytes)
            if texte is None or (famille == "inconnu" and not _ressemble_a_du_texte(texte)):
                return {"texte": None, "tronque": False, "raison": "TYPE_NON_PRIS_EN_CHARGE"}
    except Exception as e:
        import logging

        logging.error(f"ERREUR LECTURE FICHIER ({nom_fichier}) : {e}")
        return {"texte": None, "tronque": False, "raison": "ECHEC_EXTRACTION"}

    texte = (texte or "").strip()
    if not texte:
        return {"texte": None, "tronque": False, "raison": "AUCUN_TEXTE_TROUVE"}
    tronque = len(texte) > LONGUEUR_MAX_TEXTE_EXTRAIT
    if tronque:
        texte = texte[:LONGUEUR_MAX_TEXTE_EXTRAIT]
    return {"texte": texte, "tronque": tronque, "raison": None}
