"""Version anglaise des messages d'erreur Higgsfield montrés à l'utilisateur.

Les messages de `ErreurHiggsfield` sont écrits en français (l'IA les relaie telle
quelle). Quand l'interface est en anglais, la personne doit pourtant lire de
l'anglais : `message_en` traduit chaque message connu. Un message inconnu est
rendu tel quel, et le test `test_higgsfield_messages_en.py` vérifie que tous
les messages du module des requêtes sont couverts.
"""

import re

_LIBELLES = {
    "L'image de départ": "The start image",
    "L'image de fin": "The end image",
    "Les images de référence": "The reference images",
    "Les vidéos de référence": "The reference videos",
    "Les sons de référence": "The reference sounds",
    "Une image de référence": "A reference image",
    "La vidéo source": "The source video",
    "Format": "Format",
    "Qualité": "Quality",
    "Résolution": "Resolution",
}

# (motif français, modèle anglais). Les groupes nommés sont repris dans la phrase anglaise.
_MOTIFS: list[tuple[str, str]] = [
    (r"(?P<libelle>.+) doit être une adresse publique en https\.", "{libelle} must be a public https address."),
    (r"(?P<libelle>.+) \"(?P<texte>.*)\" non disponible\. Choix possibles : (?P<choix>.*)\.", "{libelle} \"{texte}\" is not available. Possible choices: {choix}."),
    (r"Maximum (?P<maximum>\d+) pour : (?P<libelle>.+)\.", "Maximum {maximum} for: {libelle}."),
    (r"Modèle vidéo \"(?P<cle>.*)\" inconnu\. Modèles disponibles : (?P<noms>.*)\.", "Unknown video model \"{cle}\". Available models: {noms}."),
    (r"Le modèle (?P<cle>.+) ne gère pas les références\. Utilise seedance\.", "The model {cle} does not handle references. Use seedance."),
    (r"Choisis : une image de départ OU des références, pas les deux\.", "Choose either a start image or references, not both."),
    (r"Des sons seuls ne suffisent pas : ajoute au moins une image ou une vidéo de référence\.", "Sounds alone are not enough: add at least one reference image or video."),
    (r"Une image de fin demande aussi une image de départ\.", "An end image also needs a start image."),
    (r"Il faut une description pour cette vidéo\.", "This video needs a description."),
    (r"Modèle d'image \"(?P<cle>.*)\" inconnu\. Modèles disponibles : (?P<noms>.*)\.", "Unknown image model \"{cle}\". Available models: {noms}."),
    (r"Il faut une description pour cette image\.", "This image needs a description."),
    (r"Le modèle (?P<cle>.+) ne gère pas les images de référence\. Utilise grok\.", "The model {cle} does not handle reference images. Use grok."),
    (r"Maximum (?P<maximum>\d+) images de référence\.", "Maximum {maximum} reference images."),
    (r"Le modèle (?P<cle>.+) n'accepte pas de style\. Utilise soul pour choisir un style\.", "The model {cle} does not accept a style. Use soul to choose a style."),
    (r"L'identifiant du style n'est pas valide : il doit s'écrire comme un UUID\.", "The style identifier is not valid: it must be written as a UUID."),
    (r"Modèle Genjutsu \"(?P<cle>.*)\" inconnu\. Modèles disponibles : (?P<noms>.*)\.", "Unknown Genjutsu model \"{cle}\". Available models: {noms}."),
    (r"Il faut une vidéo source \(adresse https\) pour Genjutsu\.", "Genjutsu needs a source video (https address)."),
    (r"Genjutsu a besoin d'au moins 1 image de référence \(1 à 8\)\.", "Genjutsu needs at least 1 reference image (1 to 8)."),
    (r"Ce modèle Genjutsu demande un preset_id \(style\)\. Liste-le d'abord ou donne son UUID\.", "This Genjutsu model needs a preset_id (style). List it first or give its UUID."),
    (r"Le modèle (?P<cle>.+) n'accepte pas de preset_id : utilise genjutsu-restyle pour les styles\.", "The model {cle} does not accept a preset_id: use genjutsu-restyle for styles."),
    (r"Impossible d'identifier l'utilisateur, génération refusée\.", "Unable to identify the user, generation refused."),
    (r"Impossible de vérifier ta limite du jour, réessaie dans un instant\.", "Unable to check your daily limit, try again in a moment."),
    (r"Limite du jour atteinte \((?P<limite>\d+) (?P<nom>.+) par jour\)\. Dis-le à l'utilisateur : il pourra en refaire demain\.", "Daily limit reached ({limite} {nom} per day). You can make more tomorrow."),
]
_COMPILES = [(re.compile(f"^{motif}$", re.DOTALL), modele) for motif, modele in _MOTIFS]


_LIBELLES_MINUSCULES = {cle.lower(): valeur.lower() for cle, valeur in _LIBELLES.items()}
_NOMS_LIMITES = {"vidéos": "videos", "images": "images", "générations MCP partagées": "shared MCP generations"}


def _libelle_en(libelle: str) -> str:
    if libelle in _LIBELLES:
        return _LIBELLES[libelle]
    # Le français met parfois le libellé en minuscules ("Maximum 8 pour : les images de référence").
    return _LIBELLES_MINUSCULES.get(libelle, libelle)


def message_en(message: str) -> str:
    """Traduit un message ErreurHiggsfield en anglais, ou le rend tel quel s'il est inconnu."""
    texte = (message or "").strip()
    for motif, modele in _COMPILES:
        trouve = motif.match(texte)
        if trouve:
            valeurs = trouve.groupdict()
            if "libelle" in valeurs:
                valeurs["libelle"] = _libelle_en(valeurs["libelle"])
            if "nom" in valeurs:
                valeurs["nom"] = _NOMS_LIMITES.get(valeurs["nom"], valeurs["nom"])
            return modele.format(**valeurs)
    return texte
