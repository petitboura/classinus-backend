"""
Outils MCP de travail sur les documents JOINTS par l'utilisateur à la conversation
(21/11/2026, demande Bourama) :

- modifier_document_conversation : modifier un Word, Excel ou PowerPoint joint
- fusionner_pdf, decouper_pdf, tourner_pages_pdf, remplir_formulaire_pdf : travail sur des PDF joints

La logique est dans core/modification_fichiers_office.py et core/travail_pdf.py (octets en
entrée, octets en sortie). Ce fichier fait le reste : retrouver le fichier joint de l'utilisateur
(même règle que lire_document_conversation : scope strict sur son compte et sur les fichiers
du chat), envoyer le résultat dans le stockage, l'enregistrer dans sa bibliothèque (origine
"ia_generee") et répondre au modèle par un TEXTE, jamais une exception.

Le fichier d'origine n'est jamais modifié : chaque outil produit un NOUVEAU fichier.

Ces outils sont sur le serveur MCP "generation" (chat) seulement, PAS sur le serveur MCP
public (core/serveur_mcp_espace.py) : à valider avec Bourama avant de les y ajouter.
"""

import logging
import re
import uuid

from core import modification_fichiers_office as office
from core import travail_pdf as pdf
from core.extraction_documents import type_document
from core.lecture_media_conversation import formater_taille, retrouver_fichier
from core.limites_media import taille_max_document_travail_octets
from core.outils_generation_commun import mcp_generation, Context, _sauvegarder_generation_bibliotheque

MIME_PDF = "application/pdf"
MIMES_OFFICE = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

ERREUR_GENERALE = "Erreur : le traitement du fichier a échoué, réessaie."


def _utilisateur(ctx: Context) -> str | None:
    if ctx is None:
        return None
    return ctx.request_context.request.query_params.get("user_id") or None


def _charger(url_fichier: str, user_id: str, familles: tuple[str, ...]):
    """
    Retrouve un fichier joint de cet utilisateur et vérifie son format et sa taille.
    Renvoie (nom, famille, octets) ou un TEXTE d'erreur pour le modèle (jamais une exception).
    """
    url_fichier = (url_fichier or "").strip()
    if not url_fichier:
        return "url_fichier manquant (le lien réel indiqué juste après le fichier joint, jamais inventé)."
    try:
        trouve = retrouver_fichier(url_fichier, user_id)
    except Exception as e:
        logging.error(f"ERREUR relecture du fichier joint (travail sur document) : {e}")
        return "Impossible de relire ce fichier pour le moment, réessaie."
    if trouve is None:
        return "Ce fichier est introuvable, ou ne t'appartient pas."
    ligne, contenu = trouve
    nom = ligne.get("nom_fichier") or "document"
    famille = type_document(nom, ligne.get("type_mime") or "")
    if famille not in familles:
        attendus = ", ".join({"pdf": "PDF", "docx": "Word (.docx)", "xlsx": "Excel (.xlsx)", "pptx": "PowerPoint (.pptx)"}[f] for f in familles)
        extra = ""
        if famille == "office_ancien":
            extra = " Les anciens formats (.doc, .xls, .ppt) ne sont pas modifiables : propose de recréer le fichier avec les outils de génération."
        return f"« {nom} » n'est pas au bon format pour cet outil (attendu : {attendus}).{extra}"
    maximum = taille_max_document_travail_octets()
    if len(contenu) > maximum:
        return f"« {nom} » est trop gros ({formater_taille(len(contenu))}) : la limite est {formater_taille(maximum)}."
    return nom, famille, contenu


def _racine(nom: str) -> str:
    """Nom sans extension, nettoyé pour servir de base à un nouveau nom de fichier."""
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", nom or "document")
    base = re.sub(r"[^\w.\- ]", "", base).strip() or "document"
    return base[:80]


def _publier(ctx: Context, octets: bytes, extension: str, type_mime: str, nom_fichier: str) -> dict:
    """
    Envoie le fichier dans le stockage public des générations et l'enregistre dans la
    bibliothèque de l'utilisateur. Renvoie {"url", "url_apercu"} (aperçu seulement pour Word,
    Excel et PowerPoint, et s'il est disponible).
    """
    from core import stockage_r2
    from core.generation_documents import BUCKET, _uploader_avec_apercu

    if extension in MIMES_OFFICE:
        resultat = _uploader_avec_apercu(octets, extension, type_mime, nom_fichier)
    else:
        chemin = f"documents/{uuid.uuid4()}.{extension}"
        stockage_r2.from_(BUCKET).upload(chemin, octets, {"content-type": type_mime})
        resultat = {"url": stockage_r2.from_(BUCKET).get_public_url(chemin), "url_apercu": None}
    _sauvegarder_generation_bibliotheque(ctx, resultat["url"], nom_fichier, type_mime)
    return resultat


def _ligne_fichier(resultat: dict) -> str:
    if resultat.get("url_apercu"):
        return f"{resultat['url']} (aperçu visuel : {resultat['url_apercu']})"
    return resultat["url"]


@mcp_generation.tool()
def modifier_document_conversation(ctx: Context, url_fichier: str, operations: list) -> str:
    """
    MODIFIE un document Word (.docx), Excel (.xlsx) ou PowerPoint (.pptx) que l'utilisateur
    a joint à la conversation, et renvoie le fichier modifié (l'original reste intact). À
    utiliser quand l'utilisateur demande de corriger, compléter, remplacer ou retirer quelque
    chose DANS son fichier ; pour créer un fichier neuf, utilise les outils de génération.
    Lis d'abord le fichier avec lire_document_conversation pour connaître son contenu exact.

    `url_fichier` : le lien réel du fichier joint (jamais inventé).
    `operations` : liste d'opérations appliquées dans l'ordre, chacune un objet avec un champ
    "action". Si une seule échoue, rien n'est livré et le message dit laquelle. Numéros de
    ligne, de diapositive et de feuille comptés à partir de 1.

    Word : {"action": "remplacer_texte", "chercher": "...", "remplacer": "..."} (partout : corps,
    tableaux, en-têtes, pieds de page, la mise en forme est gardée) ;
    {"action": "ajouter_paragraphe", "texte": "...", "apres": "texte d'un paragraphe existant"}
    ("apres" facultatif, sinon à la fin) ;
    {"action": "ajouter_titre", "texte": "...", "niveau": 1 à 3, "apres": "..."} ;
    {"action": "supprimer_paragraphe", "contenant": "...", "tous": false} ;
    {"action": "ajouter_tableau", "en_tetes": [...], "lignes": [[...]], "apres": "..."}.

    Excel : {"action": "definir_cellule", "feuille": "Notes", "cellule": "B3", "valeur": 15}
    (une valeur qui commence par = est une formule ; "feuille" facultatif = feuille active) ;
    {"action": "ajouter_ligne", "valeurs": [...]} ; {"action": "ajouter_colonne", "en_tete": "...",
    "valeurs": [...]} ; {"action": "supprimer_ligne", "numero": 4} ;
    {"action": "ajouter_feuille", "nom": "..."} ;
    {"action": "renommer_feuille", "feuille": "...", "nouveau_nom": "..."}.

    PowerPoint : {"action": "remplacer_texte", "chercher": "...", "remplacer": "..."} ;
    {"action": "ajouter_diapositive", "titre": "...", "contenu": "...", "position": 2}
    ("position" facultatif, sinon à la fin) ; {"action": "supprimer_diapositive", "numero": 3} ;
    {"action": "modifier_notes", "numero": 1, "texte": "..."}.

    Limites à dire à l'utilisateur si elles le concernent : les anciens formats (.doc, .xls,
    .ppt) ne sont pas modifiables ; ce sont les opérations ci-dessus, pas la mise en page fine
    (couleurs, polices, images).
    """
    user_id = _utilisateur(ctx)
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    try:
        charge = _charger(url_fichier, user_id, office.FAMILLES_MODIFIABLES)
        if isinstance(charge, str):
            return charge
        nom, famille, contenu = charge
        try:
            octets, comptes_rendus = office.modifier_fichier_office(famille, contenu, operations)
        except office.ErreurOperation as e:
            return f"Aucune modification livrée, {e}."
        except Exception as e:
            logging.error(f"ERREUR modification du fichier ({nom}) : {e}")
            return f"Le fichier « {nom} » n'a pas pu être modifié (fichier abîmé ou protégé), rien n'a été livré."
        nom_sortie = f"{_racine(nom)}_modifie.{famille}"
        resultat = _publier(ctx, octets, famille, MIMES_OFFICE[famille], nom_sortie)
        lignes = "\n".join(f"{i}. {c}" for i, c in enumerate(comptes_rendus, start=1))
        return f"Fichier modifié : {_ligne_fichier(resultat)}\nModifications faites :\n{lignes}\nL'original est resté intact."
    except Exception as e:
        logging.error(f"ERREUR outil modifier_document_conversation : {e}")
        return ERREUR_GENERALE


@mcp_generation.tool()
def fusionner_pdf(ctx: Context, urls_fichiers: list, nom_resultat: str = "") -> str:
    """
    FUSIONNE plusieurs PDF joints à la conversation en un seul, dans l'ordre donné. Les originaux
    restent intacts. `urls_fichiers` : les liens réels des PDF (au moins 2, 20 au plus), dans l'ordre
    voulu pour le résultat. `nom_resultat` : nom du fichier fusionné (facultatif).
    Un PDF protégé par mot de passe ne peut pas être fusionné : dis-le à l'utilisateur.
    """
    user_id = _utilisateur(ctx)
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    try:
        if not isinstance(urls_fichiers, list) or len(urls_fichiers) < 2:
            return "Il faut au moins deux PDF à fusionner (liste « urls_fichiers »)."
        noms, contenus = [], []
        for url in urls_fichiers:
            charge = _charger(url, user_id, ("pdf",))
            if isinstance(charge, str):
                return charge
            noms.append(charge[0])
            contenus.append(charge[2])
        try:
            octets, total = pdf.fusionner(contenus, noms)
        except pdf.ErreurPdf as e:
            return f"Aucune fusion livrée, {e}."
        base = _racine(nom_resultat) if nom_resultat.strip() else "fusion"
        resultat = _publier(ctx, octets, "pdf", MIME_PDF, f"{base}.pdf")
        return f"PDF fusionné ({len(contenus)} fichiers, {total} pages) : {resultat['url']}\nLes originaux sont restés intacts."
    except Exception as e:
        logging.error(f"ERREUR outil fusionner_pdf : {e}")
        return ERREUR_GENERALE


@mcp_generation.tool()
def decouper_pdf(ctx: Context, url_fichier: str, plages: list = None, pages_par_morceau: int = 0) -> str:
    """
    COUPE un PDF joint à la conversation en plusieurs PDF, ou en extrait des pages. L'original reste
    intact. Donne SOIT `plages` : une liste où chaque élément devient un PDF, par exemple
    ["1-3", "4-6", "9"] (un numéro, une plage, "8-" pour jusqu'à la fin) ; pour extraire des pages
    dans un seul PDF, une seule plage suffit, par exemple ["2-5"] ; SOIT `pages_par_morceau` : coupe
    régulièrement, par exemple 10 pour des PDF de 10 pages. Numéros de pages comptés à partir de 1.
    20 PDF au plus par appel. Pour connaître le nombre de pages, lis d'abord le fichier en mode infos
    avec lire_document_conversation.
    """
    user_id = _utilisateur(ctx)
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    try:
        charge = _charger(url_fichier, user_id, ("pdf",))
        if isinstance(charge, str):
            return charge
        nom, _, contenu = charge
        try:
            total = pdf.nombre_de_pages(contenu)
            morceaux = pdf.calculer_morceaux(total, plages, pages_par_morceau)
            sorties = [(libelle, pdf.extraire_pages(contenu, indices)) for libelle, indices in morceaux]
        except pdf.ErreurPdf as e:
            return f"Aucun découpage livré, {e}."
        base = _racine(nom)
        lignes = []
        for numero, (libelle, octets) in enumerate(sorties, start=1):
            resultat = _publier(ctx, octets, "pdf", MIME_PDF, f"{base}_{numero}.pdf")
            lignes.append(f"{numero}. {libelle} : {resultat['url']}")
        return f"« {nom} » ({total} pages) coupé en {len(sorties)} PDF :\n" + "\n".join(lignes) + "\nL'original est resté intact."
    except Exception as e:
        logging.error(f"ERREUR outil decouper_pdf : {e}")
        return ERREUR_GENERALE


@mcp_generation.tool()
def tourner_pages_pdf(ctx: Context, url_fichier: str, angle: int, pages: str = "") -> str:
    """
    TOURNE des pages d'un PDF joint à la conversation et renvoie le PDF corrigé (l'original reste
    intact). `angle` : 90 (quart de tour à droite), 180 (demi-tour) ou 270 (ou -90, quart de tour à
    gauche). `pages` : les pages à tourner, par exemple "2-4, 7" ; vide = toutes les pages. Numéros
    comptés à partir de 1.
    """
    user_id = _utilisateur(ctx)
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    try:
        charge = _charger(url_fichier, user_id, ("pdf",))
        if isinstance(charge, str):
            return charge
        nom, _, contenu = charge
        try:
            octets, nb = pdf.tourner(contenu, angle, pages)
        except pdf.ErreurPdf as e:
            return f"Aucune rotation livrée, {e}."
        resultat = _publier(ctx, octets, "pdf", MIME_PDF, f"{_racine(nom)}_pivote.pdf")
        return f"{nb} page(s) tournée(s) de {angle} degrés : {resultat['url']}\nL'original est resté intact."
    except Exception as e:
        logging.error(f"ERREUR outil tourner_pages_pdf : {e}")
        return ERREUR_GENERALE


@mcp_generation.tool()
def remplir_formulaire_pdf(ctx: Context, url_fichier: str, valeurs: dict = None) -> str:
    """
    REMPLIT un formulaire PDF joint à la conversation. Fonctionne en deux temps :
    1. Appelle d'abord SANS `valeurs` : la réponse liste les champs du formulaire (nom, type, valeur
       actuelle, choix possibles, page). Aucun fichier n'est créé.
    2. Rappelle avec `valeurs`, un objet {nom du champ: valeur}, avec les noms exacts de la liste (la
       casse est ignorée). Texte pour un champ de texte ; true ou false pour une case à cocher.
    Renvoie le PDF rempli (l'original reste intact). Ne remplis jamais un champ dont tu ne connais pas
    la valeur : demande-la à l'utilisateur. Seuls les formulaires PDF standard sont pris en charge,
    pas les formulaires de type XFA ni les documents à plat (sans champs).
    """
    user_id = _utilisateur(ctx)
    if not user_id:
        return "Erreur : utilisateur non authentifié."
    try:
        charge = _charger(url_fichier, user_id, ("pdf",))
        if isinstance(charge, str):
            return charge
        nom, _, contenu = charge
        try:
            if not valeurs:
                champs = pdf.lister_champs(contenu)
                if not champs:
                    return (
                        f"« {nom} » n'a aucun champ de formulaire remplissable (document à plat, ou formulaire "
                        "de type XFA). Dis-le à l'utilisateur."
                    )
                lignes = []
                for champ in champs:
                    morceau = f"{champ['nom']} (type {champ['type']}, page {champ['page']}"
                    if champ["valeur"]:
                        morceau += f", valeur actuelle : {champ['valeur']}"
                    if champ["choix"]:
                        morceau += f", choix : {', '.join(str(c) for c in champ['choix'])}"
                    lignes.append(morceau + ")")
                return f"Champs de « {nom} » :\n" + "\n".join(lignes)
            octets, remplis, introuvables = pdf.remplir_formulaire(contenu, valeurs)
        except pdf.ErreurPdf as e:
            return f"Aucun formulaire livré, {e}."
        resultat = _publier(ctx, octets, "pdf", MIME_PDF, f"{_racine(nom)}_rempli.pdf")
        texte = f"Formulaire rempli ({len(remplis)} champ(s) : {', '.join(remplis)}) : {resultat['url']}"
        if introuvables:
            texte += f"\nChamps introuvables, non remplis : {', '.join(introuvables)}."
        return texte + "\nL'original est resté intact."
    except Exception as e:
        logging.error(f"ERREUR outil remplir_formulaire_pdf : {e}")
        return ERREUR_GENERALE
