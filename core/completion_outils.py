"""
Completion des outils trouves par demander_outils (21/10/2026, demande Bourama).

Quand le modele demande un outil, la recherche (recherche_outils.py) ne
renvoie que les outils dont la description ressemble au besoin. Or certains
outils ne servent a rien seuls : ils vont par groupes (lire l'ecran, cliquer,
taper...) ou exigent un identifiant qu'un autre outil fournit (projectId de
Railway ou Vercel, project_id de Supabase). Ce module ajoute, a chaque outil
trouve, les outils qui doivent l'accompagner. Il ne cherche rien lui-meme et
n'appelle ni LLM ni reseau.

Les regles sont des donnees, dans registre_outils.py : GROUPES_OUTILS,
DEPENDANCES_OUTILS et FOURNISSEURS_PARAMETRES_PAR_PREFIXE.

Regles de fonctionnement :
- seuls les outils du catalogue autorise de ce tour sont ajoutes (un nom de
  regle absent du catalogue est ignore, jamais une erreur) ;
- jamais un outil deja en main, ni deja trouve ;
- l'ajout est transitif : un prerequis ajoute peut lui-meme en exiger un
  (serviceId ramene list-services, qui exige projectId, qui ramene
  list-projects) ;
- ces ajouts ne comptent pas dans le minimum ni dans le plafond de la
  recherche.
"""

from registre_outils import (
    DEPENDANCES_OUTILS,
    FOURNISSEURS_PARAMETRES_PAR_PREFIXE,
    GROUPES_OUTILS,
)

MOTIF_GROUPE = "groupe"
MOTIF_PREREQUIS = "prerequis"


def _nom(outil):
    return outil["function"]["name"]


def _parametres_obligatoires(outil):
    """Noms des parametres obligatoires d'un outil, liste vide si le schema est absent ou inattendu."""
    schema = (outil.get("function") or {}).get("parameters")
    if not isinstance(schema, dict):
        return []
    obligatoires = schema.get("required")
    return [p for p in obligatoires if isinstance(p, str)] if isinstance(obligatoires, list) else []


def _liens_de(nom, index):
    """
    Liste de (nom_lie, motif) pour l'outil `nom` : ses voisins de groupe, ses
    dependances explicites, puis les outils qui fournissent ses identifiants
    obligatoires. `index` : {nom: outil} du catalogue autorise.
    """
    liens = []
    for membres in GROUPES_OUTILS.values():
        if nom in membres:
            liens.extend((autre, MOTIF_GROUPE) for autre in membres if autre != nom)
    liens.extend((autre, MOTIF_PREREQUIS) for autre in DEPENDANCES_OUTILS.get(nom, []))
    for prefixe, fournisseurs in FOURNISSEURS_PARAMETRES_PAR_PREFIXE.items():
        if not nom.startswith(prefixe) or nom not in index:
            continue
        for parametre in _parametres_obligatoires(index[nom]):
            fournisseur = fournisseurs.get(parametre)
            if fournisseur and fournisseur != nom:
                liens.append((fournisseur, MOTIF_PREREQUIS))
    return liens


def completer_outils_trouves(trouves, catalogue_complet, deja_en_main):
    """
    Args:
        trouves: outils renvoyes par la recherche (format outils_pour_llm).
        catalogue_complet: catalogue autorise de ce tour, meme format.
        deja_en_main: ensemble des noms d'outils que le modele a deja.

    Returns:
        Liste de dicts {"outil": <outil>, "motif": "groupe" | "prerequis",
        "pour": <nom de l'outil qui l'a fait ajouter>}, dans l'ordre d'ajout.
        Vide si rien n'est a ajouter.
    """
    if not trouves or not catalogue_complet:
        return []
    index = {_nom(o): o for o in catalogue_complet}
    presents = set(deja_en_main or ()) | {_nom(o) for o in trouves}
    a_traiter = [_nom(o) for o in trouves]
    ajoutes = []
    while a_traiter:
        nom = a_traiter.pop(0)
        for lie, motif in _liens_de(nom, index):
            if lie in presents or lie not in index:
                continue
            presents.add(lie)
            ajoutes.append({"outil": index[lie], "motif": motif, "pour": nom})
            a_traiter.append(lie)
    return ajoutes


def prerequis_parmi(outils):
    """
    Pour l'ensemble final d'outils donnes au modele (trouves par la recherche
    ET ajoutes par completer_outils_trouves), indique lesquels sont des
    prerequis d'autres outils de cet ensemble.

    Returns:
        {nom du prerequis: [noms des outils de l'ensemble qui l'exigent]},
        sans doublon, dans l'ordre. Vide s'il n'y en a aucun.
    """
    index = {_nom(o): o for o in outils}
    resultat = {}
    for nom in index:
        for lie, motif in _liens_de(nom, index):
            if motif == MOTIF_PREREQUIS and lie in index and lie != nom:
                exigeants = resultat.setdefault(lie, [])
                if nom not in exigeants:
                    exigeants.append(nom)
    return resultat
