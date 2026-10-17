"""Etat du canal en direct dit au modele a chaque message (16/10/2026, demande de Bourama).

Avant, le modele ne recevait aucune phrase disant si le canal etait active ou non : il le
devinait seulement a la presence de ses outils. Ce bloc le dit clairement, et dit aussi que dans
le canal les cartes de videos et d'images ne s'affichent pas d'elles-memes : il doit donner leur
lien.

Les outils de recherche de videos et d'images disent au modele que ses cartes s'affichent quand
meme sous sa reponse s'il n'en place aucune. C'est vrai dans le chat normal, pas dans la bulle du
canal : ce bloc, ajoute en fin de prompt, precise donc la regle pour le canal actif.
"""

TEXTE_CANAL_ACTIF = (
    "\n\n## Canal en direct : ACTIVÉ\n"
    "Le canal en direct est activé pour ce message : tu vois l'écran de l'étudiant et tu peux agir "
    "dessus avec tes outils.\n"
    "Les cartes de vidéos et d'images ne s'affichent pas d'elles-mêmes dans le canal, pas même sous "
    "ta réponse (ce que disent les outils de recherche à ce sujet ne vaut que pour le chat normal). "
    "Chaque fois que tu proposes une vidéo ou une image, écris son titre puis son lien complet en "
    "clair (l'adresse qui commence par https://), sinon l'étudiant ne la verra pas."
)

TEXTE_CANAL_INACTIF = (
    "\n\n## Canal en direct : DÉSACTIVÉ\n"
    "Le canal en direct est désactivé pour ce message : tu ne vois pas l'écran de l'étudiant et tu "
    "ne peux rien faire dessus. Ne prétends jamais voir ou toucher son écran."
)


def bloc_etat_canal(canal_en_direct: bool, agent_avec_canal: bool) -> str:
    """Texte a ajouter en fin de prompt systeme.

    canal_en_direct : le canal est actif pour ce message (envoye par le frontend a chaque message).
    agent_avec_canal : l'agent peut utiliser le canal. Le texte "desactive" n'est dit qu'a lui,
    pour ne rien ajouter aux prompts des agents qui n'ont pas de canal.
    """
    if canal_en_direct:
        return TEXTE_CANAL_ACTIF
    if agent_avec_canal:
        return TEXTE_CANAL_INACTIF
    return ""
