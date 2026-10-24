"""En-tête (frontmatter) des fichiers SKILL.md.

Source de vérité : les champs Nom et Description du skill. L'en-tête du
SKILL.md est toujours recalculé à partir d'eux, pour que les deux ne divergent
jamais, quel que soit le client qui écrit (interface, script de migration...).
Les autres clés de l'en-tête et tout le corps du texte sont conservés tels quels.
"""
import json


def _ligne(cle: str, valeur: str) -> str:
    # Guillemets JSON : valides en YAML et sans risque d'injection d'une autre clé.
    return f"{cle}: {json.dumps(valeur, ensure_ascii=False)}"


def _separer(contenu: str) -> tuple[list[str], str] | None:
    """Renvoie (lignes de l'en-tête, corps) si le texte commence par un en-tête fermé."""
    if not contenu.startswith("---\n"):
        return None
    reste = contenu[4:]
    if reste.startswith("---\n") or reste == "---":
        return [], reste[4:]
    fin = reste.find("\n---")
    while fin != -1:
        apres = reste[fin + 4:]
        if apres == "" or apres.startswith("\n"):
            return reste[:fin].split("\n"), apres[1:] if apres else ""
        fin = reste.find("\n---", fin + 1)
    return None


def appliquer_entete(contenu: str, nom: str, description: str) -> str:
    """Renvoie le SKILL.md avec un en-tête dont name et description valent nom et description."""
    contenu = contenu.replace("\r\n", "\n")
    nouvelles = [_ligne("name", nom), _ligne("description", description)]
    morceau = _separer(contenu)
    if morceau is None:
        return "---\n" + "\n".join(nouvelles) + "\n---\n\n" + contenu.lstrip("\n")
    lignes, corps = morceau
    gardees, ignorer_suite = [], False
    for ligne in lignes:
        if ligne.startswith(("name:", "description:")):
            ignorer_suite = True
            continue
        if ignorer_suite and (ligne.startswith((" ", "\t")) or ligne == ""):
            continue  # suite d'une valeur sur plusieurs lignes
        ignorer_suite = False
        gardees.append(ligne)
    return "---\n" + "\n".join(nouvelles + gardees) + "\n---\n" + corps


_INDICATEURS_BLOC = (">", ">-", ">+", "|", "|-", "|+")


def _decoder(valeur: str) -> str:
    valeur = valeur.strip()
    if len(valeur) >= 2 and valeur[0] == valeur[-1] == '"':
        try:
            decode = json.loads(valeur)
            if isinstance(decode, str):
                return decode
        except ValueError:
            pass
        return valeur[1:-1]
    if len(valeur) >= 2 and valeur[0] == valeur[-1] == "'":
        return valeur[1:-1].replace("''", "'")
    return valeur


def lire_entete(contenu: str) -> dict[str, str]:
    """Lit name et description dans l'en-tête d'un SKILL.md (clés absentes : non renvoyées).

    Gère les valeurs simples, entre guillemets, et sur plusieurs lignes (blocs YAML > et |),
    qui sont ramenées sur une seule ligne.
    """
    contenu = contenu.replace("\r\n", "\n").lstrip("\ufeff")
    morceau = _separer(contenu)
    if morceau is None:
        return {}
    lignes, _ = morceau
    resultat: dict[str, str] = {}
    i = 0
    while i < len(lignes):
        cle = next((c for c in ("name", "description") if lignes[i].startswith(c + ":")), None)
        if cle is None:
            i += 1
            continue
        valeur = lignes[i][len(cle) + 1:].strip()
        suite, j = [], i + 1
        while j < len(lignes) and (lignes[j].startswith((" ", "\t")) or lignes[j] == ""):
            suite.append(lignes[j].strip())
            j += 1
        reste = " ".join(x for x in suite if x)
        if valeur in _INDICATEURS_BLOC:
            texte = reste
        elif reste and not valeur.startswith(('"', "'")):
            texte = (valeur + " " + reste).strip()
        else:
            texte = _decoder(valeur)
        resultat[cle] = texte.strip()
        i = j
    return resultat
