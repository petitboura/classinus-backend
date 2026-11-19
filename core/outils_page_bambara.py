"""
Outils de la page bambara (16/11/2026, demande de Bourama).

La page bambara ne montre que la bulle et le micro. L'utilisateur ne sait ni lire ni écrire : à part
la génération visuelle, la mémoire et la recherche (web, images, vidéos), aucun outil n'est utilisé.
Le frontend annonce la page avec `client` = `page_bambara` (voir prompt_voix_bambara.py), jamais
deviné par le serveur. Pour tout autre client, le catalogue reste exactement celui d'avant.

La liste vient des catégories de registre_outils.py (source unique) : recherche_web et memoire en
entier, plus generer_image pour la génération visuelle. Un outil ajouté plus tard à ces catégories
est donc proposé sans toucher à ce fichier.
"""

try:
    import prompt_voix_bambara
except ImportError:  # chargé comme module du paquet core
    from core import prompt_voix_bambara

from registre_outils import CATEGORIES_OUTILS

# Génération visuelle de la page. Les autres outils de génération (documents, code, sites, vidéo
# Higgsfield) n'en font pas partie pour le moment.
OUTILS_GENERATION_VISUELLE = ("generer_image",)


def noms_outils_autorises():
    """Noms des outils proposés sur la page bambara."""
    return frozenset(
        [*CATEGORIES_OUTILS["recherche_web"], *CATEGORIES_OUTILS["memoire"], *OUTILS_GENERATION_VISUELLE]
    )


def filtrer_catalogue_par_client(outils_pour_llm, table_routage, client):
    """
    Garde seulement les outils de la page bambara quand le client l'est, sinon renvoie le catalogue
    tel quel. Même forme que filtrer_catalogue_par_origine (origine_appareil.py).
    """
    if not prompt_voix_bambara.est_client_page_bambara(client):
        return outils_pour_llm, table_routage
    autorises = noms_outils_autorises()
    outils = [o for o in outils_pour_llm if o["function"]["name"] in autorises]
    table = {nom: route for nom, route in table_routage.items() if nom in autorises}
    return outils, table


def effort_reflexion_page(client, modele_force, effort_demande):
    """
    Effort de réflexion du tour. Sur la page bambara il est toujours au plus faible : « none »,
    que le modèle par défaut (DeepSeek) accepte. Si un modèle précis est imposé, on ne sait pas s'il
    accepte « none » : l'effort demandé est alors laissé tel quel, jamais inventé ici. Pour tout
    autre client, rien ne change.
    """
    if prompt_voix_bambara.est_client_page_bambara(client) and not modele_force:
        return "none"
    return effort_demande
