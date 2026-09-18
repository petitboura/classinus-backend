"""
Cree le 30/08/2026, Bourama : Lot 4 Partie 3 (app mobile), chantier
"Exploration de dossier en temps reel" (voir 00-commun-exploration-dossier.md
et 04-lecture-contenu.md a la racine du depot).

Lecture reelle du contenu d'un fichier trouve via core/exploration_dossier_mobile.py
(Lot 3) : le telephone envoie le contenu brut, encode en base64 dans la
reponse JSON du canal temps reel (core/canal_temps_reel.py, Lot 1). Ce
module choisit le traitement a appliquer selon le type MIME et renvoie un
texte exploitable par l'agent. Il ne contient aucune logique de canal
ou de dossier, uniquement la lecture.

Reutilise volontairement les circuits DEJA existants ailleurs dans le
projet plutot que d'en reconstruire :
- Image : core/description_multimedia.py::decrire_image_bibliotheque
  (vision Gemini), deja utilisee pour rendre les images de la
  bibliotheque cherchables.
- Audio : core/description_multimedia.py::transcrire_audio_bibliotheque
  (Whisper Groq), meme filtrage des hallucinations connues
  (PHRASES_HALLUCINEES_WHISPER) deja en place.
- PDF / Word (.docx) : PyPDF2 / python-docx, meme logique que
  core/bibliotheque_rag.py::extraire_texte_pdf et
  api/uploads.py::_extraire_texte_docx, dupliquee ici sur des bytes
  (et non un chemin de fichier, puisque le contenu arrive par le canal
  temps reel, jamais ecrit sur disque), meme convention de duplication
  volontaire deja assumee entre ces deux modules pour ne pas creer de
  dependance croisee entre circuits (voir leurs docstrings respectifs).
- Excel (.xlsx) : openpyxl, meme logique que
  api/uploads.py::_extraire_texte_xlsx. Pas nomme explicitement dans
  04-lecture-contenu.md mais deja disponible dans le projet et couvert
  par "tous les formats bureautiques" (00-commun-exploration-dossier.md,
  "types de fichiers a couvrir : tous, rien d'exclu a priori").

Point tranche avec Bourama le 30/08/2026 (voir 04-lecture-contenu.md,
"Point technique a trancher avec Bourama avant de coder ce lot") :
PAS de lecture pour un fichier trop volumineux pour l'instant : l'agent
le dit clairement a l'etudiant, capacite prevue plus tard, plutot que de
tenter une lecture qui risquerait de saturer le canal WebSocket. Seuils
PAR TYPE, alignes sur ceux deja en place ailleurs dans le projet pour le
meme type de fichier (api/uploads.py), pas de nouveau seuil invente ici,
sauf pour le texte brut ou aucun seuil n'existait deja.
"""

import base64
import logging

from core.extraction_contenu import extraire_segments as _extraire_segments

# Seuils alignes sur ceux deja en place dans api/uploads.py pour le meme
# type de fichier cote upload de chat. Volontairement pas de nouveau
# seuil invente pour ces types-la.
TAILLE_MAX_IMAGE_OCTETS = 5 * 1024 * 1024  # 5 Mo, meme limite que api/uploads.py (upload image chat)
TAILLE_MAX_DOCUMENT_OCTETS = 15 * 1024 * 1024  # 15 Mo, meme limite que api/uploads.py (PDF/Word/Excel chat)
TAILLE_MAX_AUDIO_OCTETS = 20 * 1024 * 1024  # 20 Mo, meme limite que api/uploads.py (limite Groq Whisper)
TAILLE_MAX_TEXTE_OCTETS = 2 * 1024 * 1024  # 2 Mo, aucun seuil existant ailleurs pour du texte brut, seuil prudent choisi ici

TYPES_IMAGE = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif",
}
TYPES_AUDIO = {
    "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a", "audio/wav", "audio/x-wav",
    "audio/aac", "audio/ogg",
}
TYPE_PDF = "application/pdf"
TYPE_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Extensions de texte brut courantes (cours, code, notes), lues telles
# quelles sans aucun traitement, comme demande dans 04-lecture-contenu.md.
EXTENSIONS_TEXTE_BRUT = {
    "txt", "md", "csv", "json", "py", "js", "ts", "tsx", "jsx", "html", "css",
    "xml", "yaml", "yml", "java", "c", "cpp", "kt", "sh", "log",
}


def _extension(nom_fichier: str) -> str:
    return nom_fichier.rsplit(".", 1)[-1].lower() if "." in (nom_fichier or "") else ""


def fichier_trop_volumineux(type_mime: str, taille_octets: int | None) -> bool:
    """
    True si `taille_octets` depasse le seuil du type concerne. False si
    la taille est inconnue (on ne bloque jamais sur une info manquante,
    seulement sur une taille reellement mesuree trop grande : l'echec
    de lecture eventuel remontera alors naturellement via lire_contenu_fichier).
    """
    if taille_octets is None:
        return False
    if type_mime in TYPES_IMAGE:
        return taille_octets > TAILLE_MAX_IMAGE_OCTETS
    if type_mime in TYPES_AUDIO:
        return taille_octets > TAILLE_MAX_AUDIO_OCTETS
    if type_mime in (TYPE_PDF, TYPE_DOCX, TYPE_XLSX):
        return taille_octets > TAILLE_MAX_DOCUMENT_OCTETS
    return taille_octets > TAILLE_MAX_TEXTE_OCTETS


def lire_contenu_fichier(contenu_base64: str, type_mime: str, nom_fichier: str) -> dict:
    """
    Decode le contenu base64 recu du telephone et applique le traitement
    adapte au type MIME. Renvoie toujours un dict :
    - {"texte": "..."} en cas de succes (texte brut, texte extrait d'un
      PDF/Word/Excel, description d'image, ou transcription audio) ;
    - {"erreur": "..."} si le traitement echoue ou si le type n'est pas
      (encore) pris en charge.

    Un seul essai, jamais de reessai automatique en cas d'echec, meme
    convention que le reste du chantier (voir
    00-commun-exploration-dossier.md, "un seul essai par
    recherche/lecture").

    18/09/2026 (étape 3 du chantier extraction/vectorisation centralisée,
    demande Bourama) : l'extraction elle-même délègue désormais à
    core/extraction_contenu.py (même module central que la bibliothèque
    privée et le catalogue public) au lieu d'une dispatch locale
    dupliquée. La liste de types couverts ici reste volontairement
    identique à avant (image/audio/PDF/Word/Excel/texte -- PAS la vidéo,
    jamais prise en charge côté téléphone jusqu'ici) : le module central
    sait aussi traiter la vidéo, mais l'étendre au téléphone n'a pas été
    demandé par Bourama, donc ce type continue de tomber dans le message
    "non pris en charge" ci-dessous plutôt que d'être silencieusement
    activé.
    """
    try:
        contenu = base64.b64decode(contenu_base64)
    except Exception as e:
        logging.error(f"ERREUR decodage base64 lecture fichier ({nom_fichier}) : {e}")
        return {"erreur": "Contenu du fichier illisible (erreur de transfert)."}

    type_reconnu = (
        type_mime in TYPES_IMAGE
        or type_mime in TYPES_AUDIO
        or type_mime in (TYPE_PDF, TYPE_DOCX, TYPE_XLSX)
        or _extension(nom_fichier) in EXTENSIONS_TEXTE_BRUT
        or (type_mime or "").startswith("text/")
    )
    if not type_reconnu:
        return {
            "erreur": f"Type de fichier non pris en charge pour la lecture pour l'instant ({type_mime or 'inconnu'})."
        }

    try:
        segments = _extraire_segments(contenu, type_mime, nom_fichier)
    except Exception as e:
        logging.error(f"ERREUR lecture fichier ({nom_fichier}, {type_mime}) : {e}")
        return {"erreur": "Échec de la lecture de ce fichier."}

    texte = "\n\n".join(segment["texte"] for segment in segments if (segment.get("texte") or "").strip())
    if not texte:
        if type_mime in TYPES_IMAGE:
            return {"erreur": "Impossible de décrire cette image."}
        if type_mime in TYPES_AUDIO:
            return {"erreur": "Impossible de transcrire cet audio (silencieux ou illisible)."}
        if type_mime == TYPE_PDF:
            return {"erreur": "Aucun texte trouvé dans ce PDF (probablement un scan sans OCR)."}
        if type_mime == TYPE_DOCX:
            return {"erreur": "Ce document Word semble vide."}
        if type_mime == TYPE_XLSX:
            return {"erreur": "Ce fichier Excel semble vide."}
        return {"erreur": "Ce fichier semble vide."}
    return {"texte": texte}
