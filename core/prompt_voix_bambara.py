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
