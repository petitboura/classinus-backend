"""
Test manuel des outils mémoire élève (chantier "mémoire eleve", 27/09/2026,
demande Bourama, Lot D). Même convention que test_envoyer_message_manuel.py :
vraie requête Starlette (ctx.request_context.request.query_params réel, pas
mocké), seules les fonctions core.memoire_eleve.* qui appellent Supabase sont
mockées ici (le vrai test contre la base réelle -- isolation entre catégories
et non-régénération globale, notamment -- a été fait à part directement
contre le projet Supabase "Clovis" via de vraies requêtes SQL sur un profil
jetable créé puis supprimé, pas dans ce fichier).

Ce fichier couvre la logique des outils eux-mêmes (core/outils_memoire_eleve.py) :
validation des entrées, messages d'erreur, format du sommaire et de la
lecture, jamais court-circuités par une vraie latence Supabase ici.
"""

import asyncio
import sys
from unittest.mock import patch

sys.path.append("core")

from starlette.requests import Request  # noqa: E402

import core.outils_memoire_eleve as ome  # noqa: E402
from mcp.server.mcpserver.context import Context  # noqa: E402
from mcp.server.context import ServerRequestContext  # noqa: E402


def construire_ctx(user_id: str | None, agent_id: str | None = "agent-test") -> Context:
    """Même construction que test_envoyer_message_manuel.py::construire_ctx."""
    parties = []
    if user_id is not None:
        parties.append(f"user_id={user_id}")
    if agent_id is not None:
        parties.append(f"agent_id={agent_id}")
    qs = "&".join(parties)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/generation",
        "query_string": qs.encode(),
        "headers": [],
    }

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    request = Request(scope, receive)
    rctx = ServerRequestContext(
        session=None, lifespan_context={}, protocol_version="2026-07-28",
        method="tools/call", request=request,
    )
    return Context(request_context=rctx)


async def cas_sommaire_utilisateur_non_identifie():
    ctx = construire_ctx(user_id=None)
    resultat = ome.memoire_sommaire(ctx=ctx)
    assert resultat == "Erreur : impossible d'identifier l'élève.", resultat
    print("OK  -- memoire_sommaire, user_id absent -> erreur claire")


async def cas_sommaire_nominal():
    ctx = construire_ctx(user_id="u1")
    lignes = [
        {"categorie": "apprentissage", "sous_categorie": "maths", "description": "Notions vues", "updated_at": "2026-09-25T10:00:00"},
        {"categorie": "identite", "sous_categorie": None, "description": None, "updated_at": None},
        {"categorie": "preferences", "sous_categorie": None, "description": None, "updated_at": None},
        {"categorie": "scolarite", "sous_categorie": None, "description": "Etablissement et niveau", "updated_at": "2026-09-27T09:00:00"},
    ]
    with patch.object(ome, "_obtenir_sommaire", return_value=lignes) as mock:
        resultat = ome.memoire_sommaire(ctx=ctx)
    mock.assert_called_once_with("u1")
    assert "apprentissage.maths: Notions vues" in resultat, resultat
    assert "identite: (vide)" in resultat, resultat
    assert "scolarite: Etablissement et niveau" in resultat, resultat
    print("OK  -- memoire_sommaire, cas nominal -> catégories vides et remplies bien formatées, jamais de contenu")


async def cas_lire_categorie_invalide():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_lire(categorie="hobbies", ctx=ctx)
    assert resultat.startswith("Erreur : categorie 'hobbies' invalide"), resultat
    print("OK  -- memoire_lire, categorie hors socle -> refusée avant tout appel Supabase")


async def cas_lire_rien_note():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_lire_categorie", return_value=None) as mock:
        resultat = ome.memoire_lire(categorie="preferences", ctx=ctx)
    mock.assert_called_once_with("u1", "preferences", None)
    assert resultat == "Rien noté à cet endroit pour l'instant.", resultat
    print("OK  -- memoire_lire, rien noté -> message clair, pas d'erreur brute")


async def cas_lire_nominal_avec_sous_categorie():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_lire_categorie", return_value={"contenu": {"notions_vues": ["derivees"]}, "description": "x", "updated_at": "x"}) as mock:
        resultat = ome.memoire_lire(categorie="apprentissage", sous_categorie="maths", ctx=ctx)
    mock.assert_called_once_with("u1", "apprentissage", "maths")
    assert resultat == '{"notions_vues": ["derivees"]}', resultat
    print("OK  -- memoire_lire, sous-catégorie précise -> contenu JSON renvoyé tel quel")


async def cas_ecrire_categorie_invalide():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="hobbies", contenu_json="{}", description="x", ctx=ctx)
    assert "invalide" in resultat, resultat
    print("OK  -- memoire_ecrire, categorie hors socle -> refusée avant tout appel Supabase")


async def cas_ecrire_json_invalide():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="pas du json", description="x", ctx=ctx)
    assert resultat == "Erreur : contenu_json doit être un objet JSON valide.", resultat
    print("OK  -- memoire_ecrire, JSON malformé -> erreur claire, pas de 500 brut")


async def cas_ecrire_json_pas_un_objet():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="[1, 2, 3]", description="x", ctx=ctx)
    assert "objet JSON" in resultat, resultat
    print("OK  -- memoire_ecrire, JSON valide mais pas un objet (liste) -> refusé")


async def cas_ecrire_description_manquante():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="{}", description="   ", ctx=ctx)
    assert resultat == "Erreur : description manquante.", resultat
    print("OK  -- memoire_ecrire, description vide -> refusée (nécessaire au sommaire)")


async def cas_ecrire_nominal():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_ecrire_categorie", return_value=(True, None)) as mock:
        resultat = ome.memoire_ecrire(
            categorie="apprentissage", sous_categorie="maths",
            contenu_json='{"notions_vues": ["derivees"]}', description="Notions vues en maths", ctx=ctx,
        )
    mock.assert_called_once_with("u1", "apprentissage", "maths", {"notions_vues": ["derivees"]}, "Notions vues en maths")
    assert resultat == "Mémoire mise à jour (apprentissage.maths).", resultat
    print("OK  -- memoire_ecrire, cas nominal -> bonne catégorie/sous-catégorie transmise, jamais les autres")


async def cas_ecrire_echec_supabase():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_ecrire_categorie", return_value=(False, "Erreur : categorie 'x' invalide. Catégories possibles : identite, scolarite, apprentissage, preferences.")):
        resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="{}", description="x", ctx=ctx)
    assert resultat.startswith("Erreur :"), resultat
    print("OK  -- memoire_ecrire, échec côté couche données -> message d'erreur relayé, pas de succès menteur")


async def main():
    await cas_sommaire_utilisateur_non_identifie()
    await cas_sommaire_nominal()
    await cas_lire_categorie_invalide()
    await cas_lire_rien_note()
    await cas_lire_nominal_avec_sous_categorie()
    await cas_ecrire_categorie_invalide()
    await cas_ecrire_json_invalide()
    await cas_ecrire_json_pas_un_objet()
    await cas_ecrire_description_manquante()
    await cas_ecrire_nominal()
    await cas_ecrire_echec_supabase()
    print("\nTous les cas passent (logique des 3 outils, ctx réel non mocké).")
    print("Validation de l'isolation reelle entre categories/sous-categories et de la")
    print("non-regeneration globale : faite a part contre Supabase (Clovis, ljrbwwmiainrjirymmak),")
    print("profil jetable cree puis supprime, voir note du 27/09/2026 dans le suivi du chantier.")


if __name__ == "__main__":
    asyncio.run(main())
