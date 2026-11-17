"""Consignes du mode vocal bambara (13/11/2026, demande de Bourama).

Quand l'utilisateur choisit « bambara » en activant le mode vocal, la chaîne est : il parle,
Soloni transcrit seulement, le texte part à l'IA de Classinus, et sa réponse est lue à voix
haute par la voix Gemini. Le frontend l'annonce avec le champ `client` de la requête de chat
(valeur `voix_bambara`), comme le plugin Thonny annonce `thonny` : jamais deviné par le serveur.

Deux notes sont alors ajoutées à la fin du prompt système, et rien d'autre ne change :
  1. tout est du texte simple, aucun élément enrichi, puisque tout est lu à voix haute ;
  2. l'utilisateur ne comprend que le bambara, ne sait ni lire ni écrire, peut seulement parler
     et écouter : l'IA répond en bambara, adapté à l'oral.
Pour tous les autres clients, le prompt est exactement celui d'avant.
"""

CLIENT_VOIX_BAMBARA = "voix_bambara"

# Page bambara (16/11/2026, demande de Bourama) : une page de Classinus qui ne montre que la bulle et
# le micro. Même chaîne vocale que ci-dessus, mais l'écran montre aussi les vidéos et les images
# que l'IA choisit, et seuls quelques outils existent. Annoncée avec `client` = `page_bambara`.
CLIENT_PAGE_BAMBARA = "page_bambara"

NOTE_TEXTE_SIMPLE = (
    "MODE VOCAL BAMBARA, note 1 : tout ce que tu écris est lu à voix haute, rien n'est affiché. "
    "Écris donc uniquement du texte simple. N'utilise aucun élément enrichi : ni fichier, ni lien, "
    "ni code, ni diagramme, ni fiche, ni QCM, ni image, ni tableau."
)

NOTE_BAMBARA_ORAL = (
    "MODE VOCAL BAMBARA, note 2 : l'utilisateur comprend uniquement le bambara. Il ne sait ni lire ni "
    "écrire, il peut seulement parler et écouter. Réponds-lui donc toujours en bambara, dans un "
    "bambara adapté à l'oral."
)


def est_client_voix_bambara(client):
    return isinstance(client, str) and client.strip().lower() == CLIENT_VOIX_BAMBARA


def consignes():
    """Les deux notes, prêtes à être ajoutées au prompt système."""
    return "\n\n" + NOTE_TEXTE_SIMPLE + "\n\n" + NOTE_BAMBARA_ORAL


NOTE_PAGE_AFFICHAGE = (
    "PAGE BAMBARA, note A : tout ce que tu écris, sauf les liens, est lu à voix haute. L'écran ne montre "
    "aucun texte : seulement des vidéos et des images. Écris donc uniquement du texte simple et court, sans "
    "fichier, code, diagramme, fiche, QCM ni tableau. Pour montrer une vidéo, écris son lien seul sur sa "
    "propre ligne. Pour montrer une image, écris-la en markdown, ![description](lien), seule sur sa ligne. "
    "La page les affiche en grand et ne lit jamais les liens à voix haute."
)

NOTE_PAGE_OUTILS = (
    "PAGE BAMBARA, note B : tu n'as ici que les outils de recherche (web, images, vidéos), de génération "
    "d'image et de mémoire. Aucun autre outil n'existe sur cette page : n'en propose aucun. Montre une "
    "vidéo ou une image chaque fois que cela aide à expliquer, puisque l'utilisateur ne peut pas lire."
)


def est_client_page_bambara(client):
    return isinstance(client, str) and client.strip().lower() == CLIENT_PAGE_BAMBARA


def consignes_page():
    """Les notes de la page bambara, prêtes à être ajoutées au prompt système."""
    return "\n\n" + NOTE_PAGE_AFFICHAGE + "\n\n" + NOTE_BAMBARA_ORAL + "\n\n" + NOTE_PAGE_OUTILS
