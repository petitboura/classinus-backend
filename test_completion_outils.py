"""
Tests du minimum d'outils et de la completion (groupes, dependances) de
demander_outils (21/10/2026). Aucun acces reseau.
"""

import sys

sys.path.append("core")  # comme les autres tests

import core.completion_outils as completion  # noqa: E402
import core.recherche_outils as recherche  # noqa: E402
from core.registre_outils import GROUPES_OUTILS  # noqa: E402


def _outil(nom, obligatoires=(), description=""):
    return {
        "type": "function",
        "function": {
            "name": nom,
            "description": description,
            "parameters": {"type": "object", "properties": {}, "required": list(obligatoires)},
        },
    }


def _noms(liste):
    return [o["function"]["name"] for o in liste]


def _noms_ajoutes(ajoutes):
    return [a["outil"]["function"]["name"] for a in ajoutes]


CATALOGUE_RAILWAY = [
    _outil("railway_list-projects"),
    _outil("railway_list-services", ["projectId"]),
    _outil("railway_get-status", ["projectId"]),
    _outil("railway_redeploy", ["environmentId", "projectId", "serviceId"]),
]


def test_identifiant_obligatoire_ajoute_son_fournisseur_et_la_chaine():
    ajoutes = completion.completer_outils_trouves([CATALOGUE_RAILWAY[3]], CATALOGUE_RAILWAY, set())
    assert set(_noms_ajoutes(ajoutes)) == {"railway_list-services", "railway_list-projects"}
    assert all(a["motif"] == completion.MOTIF_PREREQUIS for a in ajoutes)
    # list-services est ajoute pour redeploy, list-projects ensuite pour list-services (chaine)
    pour = {a["outil"]["function"]["name"]: a["pour"] for a in ajoutes}
    assert pour["railway_list-services"] == "railway_redeploy"
    assert pour["railway_list-projects"] in ("railway_redeploy", "railway_list-services")


def test_outil_qui_n_exige_que_projectId_n_ajoute_que_list_projects():
    ajoutes = completion.completer_outils_trouves([CATALOGUE_RAILWAY[2]], CATALOGUE_RAILWAY, set())
    assert _noms_ajoutes(ajoutes) == ["railway_list-projects"]


def test_rien_n_est_ajoute_deux_fois_ni_s_il_est_deja_en_main():
    ajoutes = completion.completer_outils_trouves([CATALOGUE_RAILWAY[3]], CATALOGUE_RAILWAY, {"railway_list-projects"})
    assert _noms_ajoutes(ajoutes) == ["railway_list-services"]
    ajoutes = completion.completer_outils_trouves(
        [CATALOGUE_RAILWAY[3], CATALOGUE_RAILWAY[2]], CATALOGUE_RAILWAY, set()
    )
    noms = _noms_ajoutes(ajoutes)
    assert len(noms) == len(set(noms))
    assert "railway_redeploy" not in noms and "railway_get-status" not in noms


def test_fournisseur_absent_du_catalogue_est_ignore_sans_erreur():
    catalogue = [_outil("railway_get-status", ["projectId"])]
    assert completion.completer_outils_trouves(catalogue, catalogue, set()) == []


def test_vercel_et_supabase():
    catalogue = [
        _outil("vercel_get_runtime_logs", ["projectId", "teamId"]),
        _outil("vercel_list_teams"),
        _outil("vercel_list_projects", ["teamId"]),
        _outil("supabase_execute_sql", ["project_id", "query"]),
        _outil("supabase_list_projects"),
    ]
    ajoutes = completion.completer_outils_trouves([catalogue[0]], catalogue, set())
    assert set(_noms_ajoutes(ajoutes)) == {"vercel_list_teams", "vercel_list_projects"}
    ajoutes = completion.completer_outils_trouves([catalogue[3]], catalogue, set())
    assert _noms_ajoutes(ajoutes) == ["supabase_list_projects"]


def test_dependance_explicite_notion():
    catalogue = [_outil("notion-query-multiple-data-sources"), _outil("notion-fetch"), _outil("notion-search")]
    ajoutes = completion.completer_outils_trouves([catalogue[0]], catalogue, set())
    assert _noms_ajoutes(ajoutes) == ["notion-fetch"]


def test_prerequis_parmi_donne_l_ordre_d_appel_sur_l_ensemble_final():
    final = [CATALOGUE_RAILWAY[3], CATALOGUE_RAILWAY[1], CATALOGUE_RAILWAY[0]]
    ordre = completion.prerequis_parmi(final)
    assert ordre["railway_list-services"] == ["railway_redeploy"]
    assert set(ordre["railway_list-projects"]) == {"railway_redeploy", "railway_list-services"}
    # un prerequis absent de l'ensemble final n'est pas annonce
    assert completion.prerequis_parmi([CATALOGUE_RAILWAY[3]]) == {}
    assert completion.prerequis_parmi([]) == {}


def test_groupe_donne_tous_les_membres_presents_et_ignore_les_absents():
    membres = GROUPES_OUTILS["ecran_pc"]
    catalogue = [_outil(n) for n in membres if n != "pointer_ecran"] + [_outil("autre_outil")]
    trouve = next(o for o in catalogue if _noms([o]) == ["lire_ecran"])
    ajoutes = completion.completer_outils_trouves([trouve], catalogue, set())
    attendus = set(membres) - {"lire_ecran", "pointer_ecran"}
    assert set(_noms_ajoutes(ajoutes)) == attendus
    assert all(a["motif"] == completion.MOTIF_GROUPE for a in ajoutes)


def test_groupes_sans_doublon_de_nom_entre_groupes_inattendu():
    # marquer_sujet_clos et rappeler_* ne doivent etre dans aucun groupe (main.py les force selon la taille de l'historique)
    tous = {n for membres in GROUPES_OUTILS.values() for n in membres}
    assert not ({"marquer_sujet_clos", "rappeler_echange_conversation", "rappeler_resultat_outil"} & tous)


def test_schema_absent_ou_inattendu_ne_plante_pas():
    sans_schema = {"type": "function", "function": {"name": "railway_x", "description": ""}}
    schema_bizarre = {"type": "function", "function": {"name": "railway_y", "description": "", "parameters": {"required": "projectId"}}}
    catalogue = [sans_schema, schema_bizarre, _outil("railway_list-projects")]
    assert completion.completer_outils_trouves([sans_schema, schema_bizarre], catalogue, set()) == []
    assert completion.completer_outils_trouves([], catalogue, set()) == []
    assert completion.completer_outils_trouves([sans_schema], [], set()) == []


def _catalogue_recherche(n=30):
    return [_outil(f"outil_{i}", description="envoyer message email courrier") for i in range(n)]


def test_plafond_de_securite_pour_un_besoin_tres_large():
    resultats = recherche.rechercher_outils_pertinents("envoyer message email", _catalogue_recherche())
    assert len(resultats) == recherche.PLAFOND_OUTILS_DEFAUT


def test_minimum_complete_avec_les_mieux_classes_sous_le_seuil():
    candidats = [_outil("a_envoyer", description="envoyer un message")] + [
        _outil(f"autre_{i}", description="message et " + " ".join(f"mot{j}" for j in range(40))) for i in range(8)
    ]
    resultats = recherche.rechercher_outils_pertinents("envoyer message", candidats, seuil_pertinence=0.9)
    assert len(resultats) == recherche.MINIMUM_OUTILS_DEFAUT
    assert _noms(resultats)[0] == "a_envoyer"


def test_minimum_sans_categorie_ne_prend_pas_d_outil_sans_aucun_mot_commun():
    candidats = [_outil("a_envoyer", description="envoyer un message")] + [_outil(f"x_{i}", description="calcul") for i in range(8)]
    assert _noms(recherche.rechercher_outils_pertinents("envoyer message", candidats)) == ["a_envoyer"]
    assert recherche.rechercher_outils_pertinents("zzz inconnu", candidats) == []


def test_minimum_avec_categorie_complete_meme_sans_mot_commun():
    candidats = [_outil(f"x_{i}", description="calcul") for i in range(8)]
    resultats = recherche.rechercher_outils_pertinents("zzz inconnu", candidats, completer_hors_score=True)
    assert _noms(resultats) == [f"x_{i}" for i in range(recherche.MINIMUM_OUTILS_DEFAUT)]


def test_minimum_jamais_au_dela_du_nombre_de_candidats():
    candidats = [_outil("x_0", description="calcul"), _outil("x_1", description="calcul")]
    assert len(recherche.rechercher_outils_pertinents("zzz", candidats, completer_hors_score=True)) == 2
    assert recherche.rechercher_outils_pertinents("zzz", [], completer_hors_score=True) == []
    assert recherche.rechercher_outils_pertinents("", candidats, completer_hors_score=True) == []
