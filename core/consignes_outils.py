"""
Textes ajoutes a la reponse de demander_outils (03/11/2026, demande Bourama).

Deux informations, toutes deux calculees toutes seules, jamais ecrites a la main
categorie par categorie :

1. Ce qu'il reste. Quand l'IA demande les outils d'une categorie, on lui dit combien
   d'outils de cette categorie elle n'a pas encore, et qu'elle peut redemander. Le
   nombre vient du catalogue reel du tour (outils autorises, y compris ceux des
   serveurs ajoutes par l'utilisateur), donc il suit tout seul l'origine et le
   nombre des outils. Les outils deja en main sont exclus : une nouvelle demande ne
   les redonne jamais.

2. Ce qui va ensemble. Certaines categories se combinent (GitHub et execution de
   code). Les familles sont des donnees (registre_outils.FAMILLES_OUTILS) : quand
   l'IA recoit les outils d'une categorie d'une famille, la reponse ajoute la
   consigne de combinaison, et lui rappelle de demander aussi les categories
   partenaires qu'elle n'a pas encore.

Ce module ne cherche rien, n'appelle ni LLM ni reseau, et ne touche pas au prompt
systeme.
"""

from registre_outils import FAMILLES_OUTILS, outils_de_la_categorie


def _noms(outils):
    return {o["function"]["name"] for o in outils}


def nombre_outils_restants(categorie, catalogue_complet, noms_en_main):
    """
    Nombre d'outils de `categorie` presents dans le catalogue autorise du tour que
    l'IA n'a pas encore. `noms_en_main` : noms deja disponibles ou deja trouves.
    Categorie vide ou inconnue : 0.
    """
    if not categorie or not catalogue_complet:
        return 0
    return sum(
        1 for o in outils_de_la_categorie(categorie, catalogue_complet)
        if o["function"]["name"] not in noms_en_main
    )


def texte_outils_restants(restes):
    """
    `restes` : liste de (categorie, nombre) dans l'ordre des recherches. Une meme
    categorie demandee deux fois dans le lot ne garde que le dernier nombre (le plus
    juste). Texte vide si rien ne reste.
    """
    derniers = {}
    for categorie, nombre in restes:
        derniers[categorie] = nombre
    phrases = []
    for categorie, nombre in derniers.items():
        if nombre <= 0:
            continue
        mot = "outil" if nombre == 1 else "outils"
        phrases.append(
            f"Il reste {nombre} {mot} dans la catégorie {categorie} que tu n'as pas encore. "
            "Si ce qui t'a été donné ne couvre pas ton besoin, rappelle demander_outils avec "
            "cette catégorie (ou un besoin plus précis) pour obtenir les suivants : "
            "tu ne recevras jamais deux fois le même outil."
        )
    return " ".join(phrases)


def consignes_familles(outils_trouves, outils_en_main):
    """
    Consignes de combinaison pour les categories dont l'IA vient de recevoir des outils.

    `outils_trouves` : outils donnes par cette demande.
    `outils_en_main` : outils deja disponibles ce tour-ci, plus ceux trouves.
    Renvoie un texte, vide si aucune categorie recue n'appartient a une famille.
    """
    if not outils_trouves:
        return ""
    en_main = list(outils_en_main or [])
    phrases = []
    deja_dites = set()
    for famille in FAMILLES_OUTILS.values():
        for categorie, regle in famille.items():
            if categorie in deja_dites or not outils_de_la_categorie(categorie, outils_trouves):
                continue
            deja_dites.add(categorie)
            texte = regle["consigne"]
            manquantes = [p for p in regle["avec"] if not outils_de_la_categorie(p, en_main)]
            if manquantes:
                liste = ", ".join(manquantes)
                texte += f" Tu n'as pas encore les outils de la catégorie {liste} : demande-les aussi avec demander_outils."
            phrases.append(texte)
    return " ".join(phrases)
