"""
OCR de secours pour les pages de PDF scannées (aucun texte numérique
détecté par l'extraction normale, voir core/extraction_contenu.py et
api/uploads.py:_extraire_texte_pdf).

Plan validé avec Bourama le 26/09/2026, deux passes dans cet ordre :
1) Tesseract (gratuit, local, aucun appel API) : la page est rendue en
   image via PyMuPDF (aucune dépendance système en plus de Tesseract
   lui-même, contrairement à pdf2image qui nécessite poppler), puis
   reconnue en français.
2) Si Tesseract échoue ou renvoie un résultat trop pauvre (scan de
   mauvaise qualité, formule complexe, écriture manuscrite), Gemini
   vision en filet de sécurité, en réutilisant le même prompt que
   core/description_multimedia.py (transcription intégrale du texte
   et des formules, en LaTeX pour les formules).

Le seuil "résultat pauvre" est volontairement simple (longueur du texte
utile) plutôt qu'un score de confiance Tesseract, suffisant pour
distinguer une page vide/illisible d'une page correctement reconnue
sans sur-ingénierie.
"""

import io
import logging

LONGUEUR_MIN_TEXTE_OCR_ACCEPTABLE = 20


def _rendre_page_en_image(chemin_pdf: str, numero_page: int) -> bytes | None:
    """
    Rend une page de PDF en image PNG. numero_page est 0-indexé.
    """
    try:
        import fitz

        document = fitz.open(chemin_pdf)
        page = document[numero_page]
        pixmap = page.get_pixmap(dpi=200)
        return pixmap.tobytes("png")
    except Exception as e:
        logging.error(f"ERREUR RENDU PAGE PDF EN IMAGE (page {numero_page + 1}) : {e}")
        return None


def _ocr_tesseract(image_bytes: bytes) -> str | None:
    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(image, lang="fra").strip()
    except Exception as e:
        logging.error(f"ERREUR TESSERACT (OCR page scannée) : {e}")
        return None


def extraire_texte_page_scannee(chemin_pdf: str, numero_page: int) -> str | None:
    """
    Point d'entrée unique : extrait le texte d'une page de PDF déjà
    identifiée comme scannée (aucun texte natif trouvé par l'appelant).
    Renvoie None si tout échoue, à l'appelant de traiter cette page
    comme vide, comme avant ce chantier.
    """
    image_bytes = _rendre_page_en_image(chemin_pdf, numero_page)
    if not image_bytes:
        return None

    texte_tesseract = _ocr_tesseract(image_bytes)
    if texte_tesseract and len(texte_tesseract) >= LONGUEUR_MIN_TEXTE_OCR_ACCEPTABLE:
        return texte_tesseract

    from core.description_multimedia import decrire_image_bibliotheque

    texte_gemini = decrire_image_bibliotheque(image_bytes, "image/png")
    return texte_gemini or texte_tesseract or None
