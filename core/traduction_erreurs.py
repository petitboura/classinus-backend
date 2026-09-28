"""
Traduction IA des messages d'erreur d'exécution de code (chat Classinus,
voir components/chat/SortieExecutionCode.tsx côté frontend) -- 27/09/2026,
demande Bourama (chantier "traduction erreurs execution", branche
feature/traduction-erreurs-execution).

Réutilise Gemini comme core/description_multimedia.py : même fournisseur,
même convention de module core isolé, ne dépend jamais de la couche api.
"""

import logging

from google import genai

logging.basicConfig(level=logging.INFO)

PROMPT_TRADUCTION_ERREUR = (
    "Traduis ce message d'erreur d'exécution de code Python en {langue}. "
    "Garde le sens technique intact. Ne traduis JAMAIS les identifiants de "
    "code : noms de fonctions, de variables, mots-clés Python (print, "
    "input, def, for, etc.), noms de fichiers, ni les extraits de code "
    "cités dans le message. Réponds uniquement avec la traduction, sans "
    "préambule ni commentaire."
)


def _get_secret(cle):
    import os

    return os.environ.get(cle)


def traduire_erreur_execution(texte_erreur: str, langue_cible: str) -> str | None:
    """
    Traduit `texte_erreur` (message d'erreur brut renvoyé par
    lib/useExecutionPython.ts) vers `langue_cible` (ex. "anglais",
    "arabe"), en préservant les identifiants de code. None si Gemini
    échoue ou ne renvoie rien -- l'appelant garde alors l'erreur
    originale (jamais bloquant, voir SortieExecutionCode.tsx).
    """
    try:
        client_google = genai.Client(api_key=_get_secret("GOOGLE_API_KEY"))
        reponse = client_google.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{
                "role": "user",
                "parts": [
                    {"text": PROMPT_TRADUCTION_ERREUR.format(langue=langue_cible)},
                    {"text": texte_erreur},
                ],
            }],
        )
    except Exception as e:
        logging.error(f"ERREUR GEMINI (traduction erreur exécution) : {e}")
        return None

    texte = (reponse.text or "").strip()
    return texte or None
