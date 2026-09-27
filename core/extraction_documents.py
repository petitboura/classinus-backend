"""
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
