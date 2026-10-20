"""
Vérifie chaque fournisseur de modèles avec ses vraies clés (20/10/2026).

À lancer là où les clés existent (Railway : `railway run python scripts/verifier_fournisseurs.py`,
ou un shell du service). Pour chaque modèle configuré dans Supabase, trois contrôles minuscules :
  1. texte : une phrase courte revient-elle ?
  2. outil : le modèle appelle-t-il l'outil de test, et répond-il après avoir reçu son résultat
     (aller-retour complet, y compris le renvoi de la réflexion signée) ?
  3. efforts (option --efforts) : chaque niveau d'effort annoncé au frontend est-il accepté ?

Chaque ligne dit OK ou l'erreur exacte du fournisseur (clé refusée, crédit épuisé, quota,
modèle inconnu, effort refusé). Ne modifie rien. Coût : quelques centaines de jetons par contrôle.
"""

import argparse
import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [RACINE, os.path.join(RACINE, "core")]

import fournisseurs_llm  # noqa: E402
from adaptateur_commun import CLE_ETAT_FOURNISSEUR  # noqa: E402
from clients_outils_llm import client_avec_outils  # noqa: E402
from efforts_modeles import DISTRIBUTEURS_AVEC_ADAPTATEUR, efforts_pour_modele  # noqa: E402

OUTIL_TEST = [{"type": "function", "function": {
    "name": "donner_nombre",
    "description": "Renvoie le nombre secret. À appeler pour connaître le nombre secret.",
    "parameters": {"type": "object", "properties": {}},
}}]


def lire(flux):
    texte, appels = "", {}
    for morceau in flux:
        delta = morceau.choices[0].delta
        texte += delta.content or ""
        for fragment in delta.tool_calls or []:
            appel = appels.setdefault(fragment.index, {"id": None, "name": "", "arguments": ""})
            appel["id"] = fragment.id or appel["id"]
            appel["name"] += fragment.function.name or ""
            appel["arguments"] += fragment.function.arguments or ""
    return texte, [appels[i] for i in sorted(appels)]


def controle_texte(client, modele, effort):
    flux = client.chat.completions.create(
        model=modele, reasoning_effort=effort, tools=None,
        messages=[{"role": "system", "content": "Réponds très brièvement."},
                  {"role": "user", "content": "Dis seulement le mot : bonjour"}],
    )
    texte, _ = lire(flux)
    assert texte.strip(), "réponse vide"
    return texte.strip()[:40]


def controle_outil(client, modele, effort):
    messages = [{"role": "system", "content": "Tu utilises les outils quand c'est utile. Réponds brièvement."},
                {"role": "user", "content": "Quel est le nombre secret ? Utilise l'outil."}]
    texte, appels = lire(client.chat.completions.create(
        model=modele, reasoning_effort=effort, tools=OUTIL_TEST, messages=messages))
    assert appels and appels[0]["name"] == "donner_nombre", f"aucun appel d'outil (texte reçu : {texte[:60]!r})"
    assistant = {"role": "assistant", "content": None, "tool_calls": [
        {"id": a["id"], "type": "function", "function": {"name": a["name"], "arguments": a["arguments"]}} for a in appels]}
    etat = client.etat_dernier_tour() if hasattr(client, "etat_dernier_tour") else None
    if etat:
        assistant[CLE_ETAT_FOURNISSEUR] = etat
    messages.append(assistant)
    for a in appels:
        messages.append({"role": "tool", "tool_call_id": a["id"], "content": "Le nombre secret est 4217."})
    texte, _ = lire(client.chat.completions.create(
        model=modele, reasoning_effort=effort, tools=OUTIL_TEST, messages=messages))
    assert "4217" in texte, f"réponse finale sans le résultat de l'outil : {texte[:60]!r}"
    return "outil appelé, résultat repris"


def client_pour(distributeur, modele):
    if distributeur == "deepseek":
        from openai import OpenAI
        cle = fournisseurs_llm.cle_api_du_distributeur("deepseek")
        return OpenAI(api_key=cle, base_url="https://api.deepseek.com") if cle else None
    return client_avec_outils(modele)


def essayer(nom, fonction, *arguments):
    debut = time.time()
    try:
        detail = fonction(*arguments)
        print(f"  OK      {nom:<22} {time.time() - debut:5.1f}s  {detail}")
        return True
    except Exception as erreur:  # noqa: BLE001 : on veut l'erreur exacte du fournisseur
        print(f"  ERREUR  {nom:<22} {time.time() - debut:5.1f}s  {type(erreur).__name__}: {str(erreur)[:260]}")
        return False


def main():
    analyse = argparse.ArgumentParser()
    analyse.add_argument("--efforts", action="store_true", help="teste aussi chaque niveau d'effort")
    analyse.add_argument("--fournisseur", help="un seul fournisseur : claude, gpt, gemini, grok, deepseek")
    options = analyse.parse_args()

    config = fournisseurs_llm._config_modeles()
    echecs = 0
    for distributeur in ("claude", "gpt", "gemini", "grok", "deepseek"):
        if options.fournisseur and options.fournisseur != distributeur:
            continue
        fournisseur = config["fournisseurs"].get(distributeur) or {}
        modeles = []
        for info in (config["modeles"].get(distributeur) or {}).values():
            if info["id"] not in modeles and info["id"] != "grok-build-0.1":
                modeles.append(info["id"])
        print(f"\n== {distributeur} (bientot={fournisseur.get('bientot')}, "
              f"clé {'présente' if fournisseurs_llm.cle_api_du_distributeur(distributeur) else 'ABSENTE'})")
        if not fournisseurs_llm.cle_api_du_distributeur(distributeur):
            echecs += 1
            continue
        for modele in modeles:
            client = client_pour(distributeur, modele)
            if client is None:
                print(f"  ERREUR  {modele}: aucun client")
                echecs += 1
                continue
            efforts = efforts_pour_modele(modele, distributeur)
            effort_base = "low" if "low" in efforts else (efforts[0] if efforts else None)
            print(f" {modele}  (efforts : {', '.join(efforts) or 'aucun'})")
            echecs += not essayer("texte", controle_texte, client, modele, effort_base)
            if distributeur in DISTRIBUTEURS_AVEC_ADAPTATEUR or distributeur == "deepseek":
                echecs += not essayer("outil (aller-retour)", controle_outil, client, modele, effort_base)
            if options.efforts:
                for effort in efforts:
                    echecs += not essayer(f"effort {effort}", controle_texte, client, modele, effort)
    print(f"\n{'Tout est bon.' if not echecs else f'{echecs} contrôle(s) en échec.'}")
    sys.exit(1 if echecs else 0)


if __name__ == "__main__":
    main()
