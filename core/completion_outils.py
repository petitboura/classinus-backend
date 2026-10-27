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

Regle generale (27/10/2026, demande Bourama) : pour TOUT serveur MCP, integre
ou personnalise, y compris ceux ajoutes plus tard, un parametre obligatoire
qui est un identifiant (workflowId, service_id, id...) ramene l'outil de
lecture du meme serveur qui le fournit (list_workflows...). Aucune ligne a
ajouter par serveur : le schema reel de l'outil et le nom reel des outils du
serveur suffisent. Les regles ecrites a la main restent prioritaires. Cette
regle a besoin de la table de routage (elle dit quel serveur porte quel
outil et son vrai nom) ; sans elle, seules les regles a la main s'appliquent.

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

import re

from registre_outils import (
    DEPENDANCES_OUTILS,
    FOURNISSEURS_PARAMETRES_PAR_PREFIXE,
    GROUPES_OUTILS,
    PLAFOND_FOURNISSEURS_PAR_IDENTIFIANT,
    SYNONYMES_IDENTIFIANTS,
    VERBES_FOURNISSEURS_IDENTIFIANTS,
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


def _mots(texte):
    """Mots d'un nom (camelCase, snake_case, kebab-case), en minuscules : workflowId -> [workflow, id]."""
    texte = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(texte or ""))
    return [m.lower() for m in re.split(r"[^A-Za-z0-9]+", texte) if m]


def _meme_mot(a, b):
    """Deux mots identiques au pluriel pres (workflow, workflows ; category, categories)."""
    if a == b:
        return True
    court, long_ = sorted((a, b), key=len)
    if long_ in (court + "s", court + "es"):
        return True
    return court.endswith("y") and long_ == court[:-1] + "ies"


def _mots_egaux(mots_a, mots_b):
    return len(mots_a) == len(mots_b) and all(_meme_mot(x, y) for x, y in zip(mots_a, mots_b))


def _racine_identifiant(parametre):
    """
    Mots qui nomment ce que designe un parametre identifiant, ou None si ce
    n'en est pas un : workflowId -> [workflow], service_id -> [service],
    id -> [] (a deduire du nom de l'outil), query -> None.
    """
    mots = _mots(parametre)
    if not mots or mots[-1] not in ("id", "ids"):
        return None
    return mots[:-1]


def _contexte_serveurs(index, table_routage):
    """
    Pour chaque outil du catalogue qui vient d'un serveur MCP (integre ou
    personnalise) : son serveur et son vrai nom. Les outils internes de
    Classinus n'ont pas de vrai nom dans la table : ils sont ignores.

    Returns:
        {"serveur_de": {nom: (cle_serveur, nom_reel)}, "par_serveur": {cle_serveur: [noms]}}
    """
    serveur_de = {}
    par_serveur = {}
    for nom in index:
        route = (table_routage or {}).get(nom)
        if not isinstance(route, dict) or not route.get("nom_reel"):
            continue
        cle = route.get("serveur_id") or route.get("url")
        if not cle:
            continue
        serveur_de[nom] = (cle, str(route["nom_reel"]))
        par_serveur.setdefault(cle, []).append(nom)
    return {"serveur_de": serveur_de, "par_serveur": par_serveur}


def _fournisseurs_generaux(nom, index, contexte, deja_couverts):
    """
    Regle generale : noms des outils de lecture du MEME serveur qui fournissent
    les identifiants obligatoires de `nom`, hors parametres deja couverts par
    une regle a la main.
    """
    if not contexte or nom not in contexte["serveur_de"] or nom not in index:
        return []
    cle, nom_reel = contexte["serveur_de"][nom]
    mots_outil = _mots(nom_reel)
    trouves = []
    for parametre in _parametres_obligatoires(index[nom]):
        if parametre in deja_couverts:
            continue
        racine = _racine_identifiant(parametre)
        if racine is None:
            continue
        if not racine:
            # id tout court : ce que l'outil manipule, d'apres son propre nom (get_workflow -> workflow)
            racine = mots_outil[1:] if len(mots_outil) > 1 else []
        if not racine:
            continue
        candidats = []
        for autre in contexte["par_serveur"].get(cle, []):
            if autre == nom:
                continue
            mots_autre = _mots(contexte["serveur_de"][autre][1])
            if len(mots_autre) < 2 or mots_autre[0] not in VERBES_FOURNISSEURS_IDENTIFIANTS:
                continue
            candidats.append((autre, mots_autre[1:]))
        # 2 = nom exact, 1 = contient tous les mots ou synonyme exact
        notes = []
        for autre, objet in candidats:
            if _mots_egaux(racine, objet):
                notes.append((2, autre))
            elif all(any(_meme_mot(m, o) for o in objet) for m in racine):
                notes.append((1, autre))
            elif len(racine) == 1 and any(
                racine[0] in groupe and any(_mots_egaux([syn], objet) for syn in groupe if syn != racine[0])
                for groupe in SYNONYMES_IDENTIFIANTS
            ):
                notes.append((1, autre))
        if not notes:
            continue
        meilleure = max(note for note, _ in notes)
        retenus = [autre for note, autre in notes if note == meilleure][:PLAFOND_FOURNISSEURS_PAR_IDENTIFIANT]
        trouves.extend(autre for autre in retenus if autre not in trouves)
    return trouves


def _liens_de(nom, index, contexte=None):
    """
    Liste de (nom_lie, motif) pour l'outil `nom` : ses voisins de groupe, ses
    dependances explicites, puis les outils qui fournissent ses identifiants
    obligatoires. `index` : {nom: outil} du catalogue autorise. `contexte` :
    voir _contexte_serveurs (None : pas de regle generale).
    """
    liens = []
    for membres in GROUPES_OUTILS.values():
        if nom in membres:
            liens.extend((autre, MOTIF_GROUPE) for autre in membres if autre != nom)
    liens.extend((autre, MOTIF_PREREQUIS) for autre in DEPENDANCES_OUTILS.get(nom, []))
    couverts = set()
    for prefixe, fournisseurs in FOURNISSEURS_PARAMETRES_PAR_PREFIXE.items():
        if not nom.startswith(prefixe) or nom not in index:
            continue
        for parametre in _parametres_obligatoires(index[nom]):
            fournisseur = fournisseurs.get(parametre)
            if fournisseur:
                couverts.add(parametre)
            if fournisseur and fournisseur != nom:
                liens.append((fournisseur, MOTIF_PREREQUIS))
    liens.extend((autre, MOTIF_PREREQUIS) for autre in _fournisseurs_generaux(nom, index, contexte, couverts))
    return liens


def completer_outils_trouves(trouves, catalogue_complet, deja_en_main, table_routage=None):
    """
    Args:
        trouves: outils renvoyes par la recherche (format outils_pour_llm).
        catalogue_complet: catalogue autorise de ce tour, meme format.
        deja_en_main: ensemble des noms d'outils que le modele a deja.
        table_routage: table de routage complete du tour ({nom: route}). Sans
            elle, la regle generale des identifiants ne s'applique pas.

    Returns:
        Liste de dicts {"outil": <outil>, "motif": "groupe" | "prerequis",
        "pour": <nom de l'outil qui l'a fait ajouter>}, dans l'ordre d'ajout.
        Vide si rien n'est a ajouter.
    """
    if not trouves or not catalogue_complet:
        return []
    index = {_nom(o): o for o in catalogue_complet}
    contexte = _contexte_serveurs(index, table_routage)
    presents = set(deja_en_main or ()) | {_nom(o) for o in trouves}
    a_traiter = [_nom(o) for o in trouves]
    ajoutes = []
    while a_traiter:
        nom = a_traiter.pop(0)
        for lie, motif in _liens_de(nom, index, contexte):
            if lie in presents or lie not in index:
                continue
            presents.add(lie)
            ajoutes.append({"outil": index[lie], "motif": motif, "pour": nom})
            a_traiter.append(lie)
    return ajoutes


def prerequis_parmi(outils, table_routage=None):
    """
    Pour l'ensemble final d'outils donnes au modele (trouves par la recherche
    ET ajoutes par completer_outils_trouves), indique lesquels sont des
    prerequis d'autres outils de cet ensemble. `table_routage` : la meme que
    pour completer_outils_trouves.

    Returns:
        {nom du prerequis: [noms des outils de l'ensemble qui l'exigent]},
        sans doublon, dans l'ordre. Vide s'il n'y en a aucun.
    """
    index = {_nom(o): o for o in outils}
    contexte = _contexte_serveurs(index, table_routage)
    resultat = {}
    for nom in index:
        for lie, motif in _liens_de(nom, index, contexte):
            if motif == MOTIF_PREREQUIS and lie in index and lie != nom:
                exigeants = resultat.setdefault(lie, [])
                if nom not in exigeants:
                    exigeants.append(nom)
    return resultat
