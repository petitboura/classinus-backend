"""
Sonde Vultr Serverless Inference avec la vraie clé (03/11/2026, hackathon Vultr Agent Rush).

Sert à CHOISIR les modèles avec de vrais appels, jamais en devinant les identifiants. À lancer là
où la clé existe (poste de Bourama, Railway, staging) :

    export VULTR_INFERENCE_API_KEY=...        # la clé Serverless Inference, pas la clé de l'API Vultr
    python scripts/sonder_vultr.py                          # liste les modèles que Vultr propose
    python scripts/sonder_vultr.py --modeles ID1 ID2        # teste ces modèles
    python scripts/sonder_vultr.py --tous                   # teste tous les modèles listés (peut coûter)
    python scripts/sonder_vultr.py --modeles ID1 --efforts  # teste aussi les niveaux d'effort

Pour chaque modèle, contrôles minuscules (quelques centaines de jetons chacun) :
  1. texte   : une phrase revient-elle, avec les mêmes paramètres que la boucle d'agent
               (flux, max_completion_tokens, délai) ? Donne aussi le temps du premier morceau.
  2. outil   : le modèle appelle-t-il l'outil de test, puis reprend-il le résultat ? (aller-retour complet)
  3. vision  : voit-il une image rouge envoyée en base64 ?
  4. code    : écrit-il une fonction Python qui se compile ? (le code n'est JAMAIS exécuté ici ; la
               qualité se juge en lisant la réponse affichée avec --voir-code)
  5. efforts : option --efforts, quels niveaux reasoning_effort sont acceptés ou refusés.

Chaque ligne dit OK ou l'erreur exacte de Vultr. Ne modifie rien (ni Supabase, ni Railway).
La clé n'est lue que dans l'environnement : ne la passez jamais en argument de commande.
"""

import argparse
import base64
import os
import re
import struct
import sys
import time
import zlib

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [RACINE, os.path.join(RACINE, "core")]

import fournisseurs_llm  # noqa: E402

DELAI_PAR_APPEL_SECONDES = 120
RESERVE_TOKENS_TEST = 512

OUTIL_TEST = [{"type": "function", "function": {
    "name": "donner_nombre",
    "description": "Renvoie le nombre secret. À appeler pour connaître le nombre secret.",
    "parameters": {"type": "object", "properties": {}},
}}]


def image_rouge_base64(taille=64):
    """PNG rouge uni, fabriqué ici pour ne dépendre d'aucun fichier."""
    ligne = b"\x00" + b"\xff\x00\x00" * taille

    def bloc(type_bloc, donnees):
        corps = type_bloc + donnees
        return struct.pack(">I", len(donnees)) + corps + struct.pack(">I", zlib.crc32(corps) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + bloc(b"IHDR", struct.pack(">IIBBBBB", taille, taille, 8, 2, 0, 0, 0))
        + bloc(b"IDAT", zlib.compress(ligne * taille))
        + bloc(b"IEND", b"")
    )
    return base64.b64encode(png).decode()


def lire(flux):
    """Lit un flux : (texte, appels d'outils, secondes avant le premier morceau)."""
    debut = time.time()
    premier = None
    texte, appels = "", {}
    for morceau in flux:
        if not morceau.choices:
            continue
        delta = morceau.choices[0].delta
        if premier is None and (delta.content or delta.tool_calls):
            premier = time.time() - debut
        texte += delta.content or ""
        for fragment in delta.tool_calls or []:
            appel = appels.setdefault(fragment.index, {"id": None, "name": "", "arguments": ""})
            appel["id"] = fragment.id or appel["id"]
            if fragment.function:
                appel["name"] += fragment.function.name or ""
                appel["arguments"] += fragment.function.arguments or ""
    return texte, [appels[i] for i in sorted(appels)], premier


def appeler(client, modele, messages, outils=None, **supplements):
    """Même forme d'appel que la boucle d'agent (core/boucle_agent.py:_agent_groq)."""
    return client.chat.completions.create(
        model=modele,
        messages=messages,
        max_completion_tokens=RESERVE_TOKENS_TEST,
        tools=outils,
        stream=True,
        timeout=DELAI_PAR_APPEL_SECONDES,
        **supplements,
    )


def controle_texte(client, modele):
    texte, _, premier = lire(appeler(client, modele, [
        {"role": "system", "content": "Réponds très brièvement."},
        {"role": "user", "content": "Dis seulement le mot : bonjour"},
    ]))
    assert texte.strip(), "réponse vide"
    return f"premier morceau en {premier:.1f}s, reçu : {texte.strip()[:40]!r}"


def controle_outil(client, modele):
    messages = [
        {"role": "system", "content": "Tu utilises les outils quand c'est utile. Réponds brièvement."},
        {"role": "user", "content": "Quel est le nombre secret ? Utilise l'outil."},
    ]
    texte, appels, _ = lire(appeler(client, modele, messages, OUTIL_TEST))
    assert appels and appels[0]["name"] == "donner_nombre", f"aucun appel d'outil (texte reçu : {texte[:60]!r})"
    messages.append({"role": "assistant", "content": None, "tool_calls": [
        {"id": a["id"], "type": "function", "function": {"name": a["name"], "arguments": a["arguments"] or "{}"}}
        for a in appels]})
    for a in appels:
        messages.append({"role": "tool", "tool_call_id": a["id"], "content": "Le nombre secret est 4217."})
    texte, _, _ = lire(appeler(client, modele, messages, OUTIL_TEST))
    assert "4217" in texte, f"réponse finale sans le résultat de l'outil : {texte[:60]!r}"
    return "outil appelé, résultat repris"


def controle_vision(client, modele):
    image = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_rouge_base64()}"}}
    texte, _, _ = lire(appeler(client, modele, [{"role": "user", "content": [
        {"type": "text", "text": "Quelle est la couleur de cette image ? Réponds par un seul mot."}, image]}]))
    assert re.search(r"rouge|red", texte, re.IGNORECASE), f"couleur non reconnue : {texte.strip()[:60]!r}"
    return f"image vue ({texte.strip()[:20]!r})"


def controle_code(client, modele, voir_code=False):
    texte, _, _ = lire(appeler(client, modele, [{"role": "user", "content": (
        "Écris en Python une fonction est_premier(n) qui renvoie True si n est premier. "
        "Réponds avec un seul bloc de code, sans explication.")}]))
    blocs = re.findall(r"```(?:python)?\n(.*?)```", texte, re.DOTALL)
    code = blocs[0] if blocs else texte
    assert "est_premier" in code, f"fonction absente : {texte.strip()[:60]!r}"
    compile(code, "<reponse_modele>", "exec")  # compilé seulement, jamais exécuté
    if voir_code:
        print("      ---- code reçu ----\n" + "\n".join("      " + l for l in code.splitlines()) + "\n      -------------------")
    return "code reçu et compilable (non exécuté)"


def controle_effort(client, modele, effort):
    texte, _, _ = lire(appeler(client, modele, [{"role": "user", "content": "Dis seulement : bonjour"}],
                               reasoning_effort=effort))
    assert texte.strip(), "réponse vide"
    return "accepté"


def essayer(nom, fonction, *arguments):
    debut = time.time()
    try:
        detail = fonction(*arguments)
        print(f"  OK      {nom:<22} {time.time() - debut:5.1f}s  {detail}")
        return True
    except Exception as erreur:  # noqa: BLE001 : on veut l'erreur exacte de Vultr
        print(f"  ERREUR  {nom:<22} {time.time() - debut:5.1f}s  {type(erreur).__name__}: {str(erreur)[:300]}")
        return False


def lister_modeles(client):
    modeles = list(client.models.list())
    print(f"{len(modeles)} modèle(s) proposé(s) par {fournisseurs_llm.adresse_vultr()} :")
    for m in modeles:
        supplements = getattr(m, "model_extra", None) or {}
        print(f"  {m.id}" + (f"   {supplements}" if supplements else ""))
    return [m.id for m in modeles]


def main():
    analyse = argparse.ArgumentParser(description="Sonde Vultr Serverless Inference avec de vrais appels.")
    analyse.add_argument("--modeles", nargs="+", help="identifiants à tester, tels que listés par Vultr")
    analyse.add_argument("--tous", action="store_true", help="teste tous les modèles listés")
    analyse.add_argument("--efforts", action="store_true", help="teste aussi les niveaux reasoning_effort")
    analyse.add_argument("--voir-code", action="store_true", help="affiche le code reçu pour juger la qualité")
    options = analyse.parse_args()

    variable = fournisseurs_llm.VARIABLE_CLE_VULTR
    client = fournisseurs_llm.creer_client_vultr(os.environ.get(variable))
    if client is None:
        print(f"Clé absente : définissez la variable d'environnement {variable} (clé Serverless Inference).")
        sys.exit(2)

    try:
        disponibles = lister_modeles(client)
    except Exception as erreur:  # noqa: BLE001
        print(f"ERREUR  liste des modèles : {type(erreur).__name__}: {str(erreur)[:300]}")
        print("Si le réseau refuse Vultr depuis ici, lancez ce script depuis Railway ou le staging.")
        sys.exit(1)

    a_tester = disponibles if options.tous else (options.modeles or [])
    if not a_tester:
        print("\nChoisissez des modèles avec --modeles (ou --tous) pour les tester.")
        return
    inconnus = [m for m in a_tester if m not in disponibles]
    if inconnus:
        print(f"\nAttention, absents de la liste Vultr : {', '.join(inconnus)}")

    echecs = 0
    for modele in a_tester:
        print(f"\n== {modele}")
        echecs += not essayer("texte", controle_texte, client, modele)
        echecs += not essayer("outil (aller-retour)", controle_outil, client, modele)
        echecs += not essayer("vision", controle_vision, client, modele)
        echecs += not essayer("code", controle_code, client, modele, options.voir_code)
        if options.efforts:
            for effort in ("none", "low", "medium", "high"):
                echecs += not essayer(f"effort {effort}", controle_effort, client, modele, effort)
    print(f"\n{'Tout est bon.' if not echecs else f'{echecs} contrôle(s) en échec.'}")
    sys.exit(1 if echecs else 0)


if __name__ == "__main__":
    main()
