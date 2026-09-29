"""
Test manuel des outils mémoire élève (chantier "mémoire eleve", 27/09/2026,
demande Bourama, Lot D). Même convention que test_envoyer_message_manuel.py :
vraie requête Starlette (ctx.request_context.request.query_params réel, pas
mocké), seules les fonctions core.memoire_eleve.* qui appellent Supabase sont
mockées ici (le vrai test contre la base réelle, isolation entre catégories
et non-régénération globale, notamment, a été fait à part directement
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
    print("OK : memoire_sommaire, user_id absent -> erreur claire")


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
    print("OK : memoire_sommaire, cas nominal -> catégories vides et remplies bien formatées, jamais de contenu")


async def cas_lire_categorie_invalide():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_lire(categorie="hobbies", ctx=ctx)
    assert resultat.startswith("Erreur : categorie 'hobbies' invalide"), resultat
    print("OK : memoire_lire, categorie hors socle -> refusée avant tout appel Supabase")


async def cas_lire_rien_note():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_lire_categorie", return_value=None) as mock:
        resultat = ome.memoire_lire(categorie="preferences", ctx=ctx)
    mock.assert_called_once_with("u1", "preferences", None)
    assert resultat == "Rien noté à cet endroit pour l'instant.", resultat
    print("OK : memoire_lire, rien noté -> message clair, pas d'erreur brute")


async def cas_lire_nominal_avec_sous_categorie():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_lire_categorie", return_value={"contenu": {"notions_vues": ["derivees"]}, "description": "x", "updated_at": "x"}) as mock:
        resultat = ome.memoire_lire(categorie="apprentissage", sous_categorie="maths", ctx=ctx)
    mock.assert_called_once_with("u1", "apprentissage", "maths")
    assert resultat == '{"notions_vues": ["derivees"]}', resultat
    print("OK : memoire_lire, sous-catégorie précise -> contenu JSON renvoyé tel quel")


async def cas_ecrire_categorie_invalide():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="hobbies", contenu_json="{}", description="x", ctx=ctx)
    assert "invalide" in resultat, resultat
    print("OK : memoire_ecrire, categorie hors socle -> refusée avant tout appel Supabase")


async def cas_ecrire_json_invalide():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="pas du json", description="x", ctx=ctx)
    assert resultat == "Erreur : contenu_json doit être un objet JSON valide.", resultat
    print("OK : memoire_ecrire, JSON malformé -> erreur claire, pas de 500 brut")


async def cas_ecrire_json_pas_un_objet():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="[1, 2, 3]", description="x", ctx=ctx)
    assert "objet JSON" in resultat, resultat
    print("OK : memoire_ecrire, JSON valide mais pas un objet (liste) -> refusé")


async def cas_ecrire_description_manquante():
    ctx = construire_ctx(user_id="u1")
    resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="{}", description="   ", ctx=ctx)
    assert resultat == "Erreur : description manquante.", resultat
    print("OK : memoire_ecrire, description vide -> refusée (nécessaire au sommaire)")


async def cas_ecrire_nominal():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_ecrire_categorie", return_value=(True, None)) as mock:
        resultat = ome.memoire_ecrire(
            categorie="apprentissage", sous_categorie="maths",
            contenu_json='{"notions_vues": ["derivees"]}', description="Notions vues en maths", ctx=ctx,
        )
    mock.assert_called_once_with("u1", "apprentissage", "maths", {"notions_vues": ["derivees"]}, "Notions vues en maths")
    assert resultat == "Mémoire mise à jour (apprentissage.maths).", resultat
    print("OK : memoire_ecrire, cas nominal -> bonne catégorie/sous-catégorie transmise, jamais les autres")


async def cas_ecrire_echec_supabase():
    ctx = construire_ctx(user_id="u1")
    with patch.object(ome, "_ecrire_categorie", return_value=(False, "Erreur : categorie 'x' invalide. Catégories possibles : identite, scolarite, apprentissage, preferences.")):
        resultat = ome.memoire_ecrire(categorie="scolarite", contenu_json="{}", description="x", ctx=ctx)
    assert resultat.startswith("Erreur :"), resultat
    print("OK : memoire_ecrire, échec côté couche données -> message d'erreur relayé, pas de succès menteur")


def _outil(nom):
    return {"type": "function", "function": {"name": nom, "description": "", "parameters": {}}}


async def cas_injection_ajoute_les_3_outils_et_leur_routage():
    from core.routage_outils import _outils_memoire_toujours_disponibles
    catalogue = [_outil("recherche_web"), _outil("memoire_sommaire"), _outil("memoire_lire"), _outil("memoire_ecrire")]
    routage_complet = {n: {"url": f"http://x/{n}", "headers": None} for n in ("recherche_web", "memoire_sommaire", "memoire_lire", "memoire_ecrire")}
    outils_mcp = [_outil("recherche_web")]
    table_routage = {"recherche_web": routage_complet["recherche_web"]}
    outils_avant, table_avant = list(outils_mcp), dict(table_routage)

    outils, table = _outils_memoire_toujours_disponibles(outils_mcp, table_routage, catalogue, routage_complet)

    noms = [o["function"]["name"] for o in outils]
    assert noms == ["recherche_web", "memoire_sommaire", "memoire_lire", "memoire_ecrire"], noms
    for n in ("memoire_sommaire", "memoire_lire", "memoire_ecrire"):
        assert table[n] == routage_complet[n], n
    assert outils_mcp == outils_avant and table_routage == table_avant, "les entrees ne doivent pas etre modifiees en place"
    print("OK  -- injection : 3 outils ajoutes a outils_mcp ET a table_routage, entrees d'origine intactes")


async def cas_injection_sans_doublon():
    from core.routage_outils import _outils_memoire_toujours_disponibles
    catalogue = [_outil("memoire_sommaire"), _outil("memoire_lire"), _outil("memoire_ecrire")]
    routage_complet = {n: {"url": "u", "headers": None} for n in ("memoire_sommaire", "memoire_lire", "memoire_ecrire")}
    outils, _ = _outils_memoire_toujours_disponibles([_outil("memoire_lire")], dict(routage_complet), catalogue, routage_complet)
    noms = [o["function"]["name"] for o in outils]
    assert sorted(noms) == ["memoire_ecrire", "memoire_lire", "memoire_sommaire"] and len(noms) == 3, noms
    print("OK  -- injection : un outil deja propose par le routeur n'est pas ajoute en double")


async def cas_injection_catalogue_sans_outils_memoire():
    from core.routage_outils import _outils_memoire_toujours_disponibles
    outils, table = _outils_memoire_toujours_disponibles([_outil("a")], {"a": {}}, [_outil("a")], {"a": {}})
    assert [o["function"]["name"] for o in outils] == ["a"] and list(table) == ["a"]
    print("OK  -- injection : catalogue sans les 3 outils (migration pas appliquee) -> rien ajoute, aucune erreur")


async def cas_injection_entrees_none():
    from core.routage_outils import _outils_memoire_toujours_disponibles
    outils, table = _outils_memoire_toujours_disponibles(None, None, [_outil("memoire_sommaire")], {"memoire_sommaire": {"url": "u"}})
    assert [o["function"]["name"] for o in outils] == ["memoire_sommaire"] and "memoire_sommaire" in table
    print("OK  -- injection : outils_mcp et table_routage a None (aucun outil pour ce tour) -> gere")


async def cas_regle_systeme_selon_user_id():
    import construction_system_prompt as csp
    with patch.object(csp, "get_system_prompt", return_value="PROMPT_BASE"):
        connecte = csp._construire_system_prompt("bonjour", "agent-test", "u1")
        visiteur = csp._construire_system_prompt("bonjour", "agent-test", None)
    assert "<memoire_eleve>" in connecte, "la regle memoire doit etre presente pour un utilisateur connecte"
    assert "<memoire_eleve>" not in visiteur, "la regle memoire ne doit pas etre presente pour un visiteur sans compte"
    assert "n'annonce jamais" in connecte, "la regle memoire doit imposer la discretion (ne jamais annoncer qu'on consulte ou enregistre)"
    assert "pas à chaque message" in connecte, "la regle memoire doit limiter l'usage aux moments utiles"
    print("OK  -- prompt systeme : regle memoire presente pour un utilisateur connecte, absente pour un visiteur")


class _FauxSupabase:
    """Imite la chaine supabase-py utilisee par core/memoire_eleve.py, avec le
    comportement REEL de la version installee : maybe_single().execute()
    renvoie None (et non un objet vide) quand aucune ligne n'existe."""

    def __init__(self, lignes=None, unique=None, echec=False):
        self.lignes, self.unique, self.echec = lignes or [], unique, False or echec
        self.appels = []

    def table(self, nom):
        self.appels.append(("table", nom))
        return self

    def select(self, *a):
        self.appels.append(("select", a))
        return self

    def eq(self, col, val):
        self.appels.append(("eq", col, val))
        return self

    def maybe_single(self):
        self.appels.append(("maybe_single",))
        self._single = True
        return self

    def upsert(self, ligne, on_conflict=None):
        self.appels.append(("upsert", ligne, on_conflict))
        self._upsert = True
        return self

    def execute(self):
        if self.echec:
            raise RuntimeError("panne simulee")
        if getattr(self, "_single", False):
            self._single = False
            return None if self.unique is None else type("R", (), {"data": self.unique})()
        return type("R", (), {"data": self.lignes})()


async def cas_couche_donnees_lecture_ligne_absente():
    import core.memoire_eleve as me
    faux = _FauxSupabase(unique=None)
    with patch.object(me, "_supabase_memoire", faux):
        assert me.lire_categorie("u1", "scolarite") is None
    assert ("eq", "sous_categorie", "") in faux.appels, faux.appels
    print("OK : couche donnees, lecture d'une categorie jamais ecrite (maybe_single -> None) : renvoie None sans erreur")


async def cas_couche_donnees_lecture_ligne_presente():
    import core.memoire_eleve as me
    ligne = {"contenu": {"niveau": "MP1"}, "description": "d", "updated_at": "t"}
    with patch.object(me, "_supabase_memoire", _FauxSupabase(unique=ligne)):
        assert me.lire_categorie("u1", "scolarite") == ligne
    print("OK : couche donnees, lecture d'une categorie existante : contenu renvoye")


async def cas_couche_donnees_lecture_panne():
    import core.memoire_eleve as me
    with patch.object(me, "_supabase_memoire", _FauxSupabase(echec=True)):
        assert me.lire_categorie("u1", "scolarite") is None
    print("OK : couche donnees, panne Supabase a la lecture : None, jamais d'exception")


async def cas_couche_donnees_sommaire_complete_le_socle():
    import core.memoire_eleve as me
    lignes = [{"categorie": "apprentissage", "sous_categorie": "maths", "description": "d", "updated_at": "t"}]
    with patch.object(me, "_supabase_memoire", _FauxSupabase(lignes=lignes)):
        res = me.obtenir_sommaire("u1")
    racines = {(l["categorie"], l["sous_categorie"]) for l in res}
    for c in me.CATEGORIES_MEMOIRE_ELEVE:
        assert (c, None) in racines, (c, racines)
    assert ("apprentissage", "maths") in racines
    print("OK : couche donnees, sommaire : 4 categories du socle toujours presentes, sous-categories conservees")


async def cas_couche_donnees_ecriture_racine_et_sous_categorie():
    import core.memoire_eleve as me
    faux = _FauxSupabase()
    with patch.object(me, "_supabase_memoire", faux):
        ok, err = me.ecrire_categorie("u1", "scolarite", None, {"a": 1}, "d")
        ok2, _ = me.ecrire_categorie("u1", "apprentissage", "maths", {"b": 2}, "d2")
    ups = [a for a in faux.appels if a[0] == "upsert"]
    assert ok and err is None and ok2
    assert ups[0][1]["sous_categorie"] == "" and ups[1][1]["sous_categorie"] == "maths", ups
    assert all(u[2] == "user_id,categorie,sous_categorie" for u in ups), ups
    print("OK : couche donnees, ecriture : racine = chaine vide, sous-categorie conservee, cle de conflit correcte")


async def cas_couche_donnees_ecriture_categorie_hors_socle_sans_appel_base():
    import core.memoire_eleve as me
    faux = _FauxSupabase()
    with patch.object(me, "_supabase_memoire", faux):
        ok, err = me.ecrire_categorie("u1", "hobbies", None, {}, "d")
    assert not ok and "invalide" in err and not any(a[0] == "upsert" for a in faux.appels)
    print("OK : couche donnees, categorie hors socle : refusee avant tout appel a la base")


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
    await cas_injection_ajoute_les_3_outils_et_leur_routage()
    await cas_injection_sans_doublon()
    await cas_injection_catalogue_sans_outils_memoire()
    await cas_injection_entrees_none()
    await cas_regle_systeme_selon_user_id()
    await cas_couche_donnees_lecture_ligne_absente()
    await cas_couche_donnees_lecture_ligne_presente()
    await cas_couche_donnees_lecture_panne()
    await cas_couche_donnees_sommaire_complete_le_socle()
    await cas_couche_donnees_ecriture_racine_et_sous_categorie()
    await cas_couche_donnees_ecriture_categorie_hors_socle_sans_appel_base()
    print("\nTous les cas passent (outils, injection, regle systeme, couche donnees).")
    print("Validation de l'isolation reelle entre categories/sous-categories et de la")
    print("non-regeneration globale : faite a part contre Supabase (Clovis, ljrbwwmiainrjirymmak),")
    print("profil jetable cree puis supprime, voir note du 27/09/2026 dans le suivi du chantier.")


if __name__ == "__main__":
    asyncio.run(main())
