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
