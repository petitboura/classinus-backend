"""Consignes du mode vocal bambara (13/11/2026, demande de Bourama).

Quand l'utilisateur choisit « bambara » en activant le mode vocal, la chaîne est : il parle,
Soloni transcrit seulement, le texte part à l'IA de Classinus, et sa réponse est lue à voix
haute par la voix Gemini. Le frontend l'annonce avec le champ `client` de la requête de chat
(valeur `voix_bambara`), comme le plugin Thonny annonce `thonny` : jamais deviné par le serveur.

Quatre notes sont alors ajoutées à la fin du prompt système, et rien d'autre ne change :
  1. le texte reste simple et lu à voix haute : aucun élément écrit (fichier, code, diagramme,
     fiche, QCM, tableau). Les images et les vidéos sont permises, voir la note 3 ;
  2. l'utilisateur ne comprend que le bambara, ne sait ni lire ni écrire, peut seulement parler
     et écouter : l'IA répond en bambara, adapté à l'oral ;
  3. (14/11/2026, demande de Bourama) l'IA privilégie obligatoirement les visuels, images et
     vidéos, plutôt que la voix seule : ils se comprennent sans savoir lire ;
  4. (14/11/2026, demande de Bourama) quand l'IA ne sait pas, elle cherche en ligne avec ses
     outils de recherche au lieu de répondre « je ne sais pas ».
Pour tous les autres clients, le prompt est exactement celui d'avant.

Les outils de recherche listés dans OUTILS_TOUJOURS_VOIX_BAMBARA sont donnés à l'IA à chaque
message de ce client, sans passer par demander_outils (branchement dans core/main.py, qui
utilise core/routage_outils.py::_outils_memoire_toujours_disponibles).
"""

CLIENT_VOIX_BAMBARA = "voix_bambara"

# Outils donnés à chaque message du client voix_bambara (14/11/2026, demande de Bourama) :
# la recherche web, la recherche d'image, la recherche de vidéo et la lecture d'une vidéo.
# Volontairement sans tavily_extract, tavily_crawl, tavily_map ni tavily_research.
# Pour changer la liste, il suffit de modifier ce tuple.
OUTILS_TOUJOURS_VOIX_BAMBARA = (
    "tavily_search", "rechercher_image", "rechercher_video", "lire_video",
)

# Page bambara (16/11/2026, demande de Bourama) : une page de Classinus qui ne montre que la bulle et
# le micro. Même chaîne vocale que ci-dessus, mais l'écran montre aussi les vidéos et les images
# que l'IA choisit, et seuls quelques outils existent. Annoncée avec `client` = `page_bambara`.
CLIENT_PAGE_BAMBARA = "page_bambara"

NOTE_TEXTE_SIMPLE = (
    "MODE VOCAL BAMBARA, note 1 : ton texte est lu à voix haute. Écris donc uniquement du texte "
    "simple. N'utilise aucun élément écrit : ni fichier, ni code, ni diagramme, ni fiche, ni QCM, "
    "ni tableau. Les images et les vidéos, elles, sont permises et même obligatoires quand c'est "
    "possible : voir la note 3."
)

NOTE_BAMBARA_ORAL = (
    "MODE VOCAL BAMBARA, note 2 : l'utilisateur comprend uniquement le bambara. Il ne sait ni lire ni "
    "écrire, il peut seulement parler et écouter. Réponds-lui donc toujours en bambara, dans un "
    "bambara adapté à l'oral."
)

NOTE_VISUELS = (
    "MODE VOCAL BAMBARA, note 3 : tu dois désormais, obligatoirement, privilégier les visuels, "
    "images et vidéos, plutôt que la voix seule. L'utilisateur comprend ce qu'il voit sans avoir "
    "besoin de lire : dès qu'une image ou une vidéo peut montrer ou expliquer ce qu'il demande, "
    "montre-la, en plus de ta réponse parlée, et ne te contente jamais de la voix seule quand un "
    "visuel existe. Tes outils de recherche (recherche web, recherche d'image, recherche de vidéo, "
    "lecture d'une vidéo) sont déjà dans ta liste à chaque message : appelle-les directement, sans "
    "passer par demander_outils et sans demander la permission."
)

NOTE_RECHERCHE = (
    "MODE VOCAL BAMBARA, note 4 : quand tu ne connais pas la réponse, quand tu hésites, ou quand "
    "l'information peut avoir changé, tu ne réponds jamais simplement « je ne sais pas ». Tu "
    "cherches d'abord en ligne avec tes outils de recherche (recherche web, recherche d'image, "
    "recherche de vidéo), tout de suite, sans demander la permission, puis tu réponds avec ce que "
    "tu as trouvé. Tu ne dis que tu n'as rien trouvé qu'après avoir réellement cherché et que la "
    "recherche n'a rien donné d'utilisable : dans ce cas, dis-le honnêtement, en bambara."
)


def est_client_voix_bambara(client):
    return isinstance(client, str) and client.strip().lower() == CLIENT_VOIX_BAMBARA


def consignes():
    """Les quatre notes, prêtes à être ajoutées au prompt système."""
    return (
        "\n\n" + NOTE_TEXTE_SIMPLE + "\n\n" + NOTE_BAMBARA_ORAL
        + "\n\n" + NOTE_VISUELS + "\n\n" + NOTE_RECHERCHE
    )


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

# 22/11/2026, demande de Bourama : cette règle ne vaut QUE pour la page bambara, pas pour le reste de la
# plateforme (les consignes de rechercher_image et rechercher_video restent celles de tout le monde). Sur la
# page, l'écran ne montre que des images et des vidéos et l'utilisateur ne sait pas lire : la quantité compte
# autant que la qualité, et le tri du modèle sert à écarter les résultats hors sujet, pas à élire les meilleurs.
NOTE_PAGE_QUANTITE = (
    "PAGE BAMBARA, note C : sur cette page, la quantité compte autant que la qualité. Quand tu cherches des "
    "images ou des vidéos, ton tri sert UNIQUEMENT à écarter ce qui ne correspond pas à la demande, pas à "
    "choisir les plus pertinentes. Dès qu'une image ou une vidéo correspond, même si elle est moyenne, montre-la "
    "plutôt que d'en garder seulement quelques-unes. Écris-les à la suite, chacune seule sur sa ligne, sans ligne "
    "vide entre elles : la page les range ensemble. S'il t'en reste peu après le tri, rappelle l'outil avec "
    "page=2 pour en trouver davantage. Si aucune ne correspond, n'en montre aucune."
)


# 23/11/2026, demande de Bourama : la réponse n'est plus un seul bloc. La page découpe ce que le modèle écrit en blocs
# (un paragraphe de texte, une série d'images, une série de vidéos), dans l'ordre où il les écrit, et lit chaque bloc de
# texte à part. C'est donc au modèle d'organiser sa réponse. Les images qu'il crée avec l'outil de génération ne sont
# plus montrées d'office : elles n'apparaissent que s'il écrit lui-même leur lien.
NOTE_PAGE_BLOCS = (
    "PAGE BAMBARA, note D : la page découpe ta réponse en blocs, affichés et lus séparément dans l'ordre où tu les "
    "écris. Chaque paragraphe de texte, séparé du suivant par une ligne vide, devient un bloc lu à part : écris des "
    "paragraphes courts, une idée par paragraphe. Place chaque image ou vidéo exactement à l'endroit où elle doit "
    "apparaître, entre deux paragraphes ou entre d'autres visuels, chacune seule sur sa ligne. Des images (ou des "
    "vidéos) écrites à la suite, sans texte entre elles, forment un seul bloc : pour les séparer, mets un paragraphe "
    "de texte entre elles, ou une vidéo entre des images. Une image que tu crées avec l'outil de génération "
    "n'apparaît que si tu écris toi-même son lien, en markdown, ![description](lien), seule sur sa ligne : écris-le "
    "toujours. Un même lien ne s'affiche qu'une fois."
)


def est_client_page_bambara(client):
    return isinstance(client, str) and client.strip().lower() == CLIENT_PAGE_BAMBARA


def consignes_page():
    """Les notes de la page bambara, prêtes à être ajoutées au prompt système."""
    return (
        "\n\n" + NOTE_PAGE_AFFICHAGE + "\n\n" + NOTE_BAMBARA_ORAL + "\n\n" + NOTE_PAGE_OUTILS
        + "\n\n" + NOTE_PAGE_QUANTITE + "\n\n" + NOTE_PAGE_BLOCS
    )
