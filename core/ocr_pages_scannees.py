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


# Alias public : même fonction, utilisable directement sur une image
# quelconque (pas seulement une page de PDF rendue) -- voir
# core/main.py, chemin image du chat (27/09/2026, demande Bourama).
ocr_tesseract_image = _ocr_tesseract


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

    # Coupe-circuit quota Gemini existant (core/embeddings.py, partagé
    # par toutes les files de vectorisation) : si la porte est déjà
    # fermée suite à un quota épuisé ailleurs dans le projet, on
    # n'ajoute pas des appels Gemini voués à échouer en plus, page par
    # page, sur un même document scanné. Le texte Tesseract (même
    # pauvre) reste utilisé s'il y en a un.
    from core.embeddings import est_en_pause_quota_gemini

    if est_en_pause_quota_gemini():
        return texte_tesseract or None

    from core.description_multimedia import decrire_image_bibliotheque

    texte_gemini = decrire_image_bibliotheque(image_bytes, "image/png")
    return texte_gemini or texte_tesseract or None


CONFIANCE_MIN_TESSERACT_IMAGE_CHAT = 75
MOTS_MIN_TESSERACT_IMAGE_CHAT = 8


def ocr_tesseract_image_fiable(image_bytes: bytes) -> str | None:
    """
    Pour les images jointes au chat : contrairement à une page de PDF
    scannée (où le texte est le but), une image peut être une photo ou
    un schéma où Tesseract sortirait du bruit de plus de 20 caractères.
    On ne garde donc son texte que si la confiance moyenne de
    reconnaissance est élevée et si assez de mots sont reconnus.
    Renvoie None dans tous les autres cas : l'appelant utilise Gemini.
    """
    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        donnees = pytesseract.image_to_data(image, lang="fra", output_type=pytesseract.Output.DICT)
        confiances = []
        for mot, conf in zip(donnees["text"], donnees["conf"]):
            if mot and mot.strip():
                try:
                    valeur = float(conf)
                except (TypeError, ValueError):
                    continue
                if valeur >= 0:
                    confiances.append(valeur)
        if len(confiances) < MOTS_MIN_TESSERACT_IMAGE_CHAT:
            return None
        if sum(confiances) / len(confiances) < CONFIANCE_MIN_TESSERACT_IMAGE_CHAT:
            return None
        texte = pytesseract.image_to_string(image, lang="fra").strip()
        return texte or None
    except Exception as e:
        logging.error(f"ERREUR TESSERACT (image chat) : {e}")
        return None
