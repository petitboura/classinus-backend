"""Comparaison entre l'adresse d'un serveur MCP et le site officiel de l'outil (27/10/2026, demande de Bourama).

Quand l'IA propose d'ajouter un serveur MCP qu'elle a trouvé sur internet, la carte affichée à
l'utilisateur doit dire si l'adresse vient bien du site officiel de l'outil. Ce n'est pas à l'IA
de l'affirmer : elle donne l'adresse du serveur et l'adresse du site officiel, et ce module
compare les deux noms de domaine. Rien ne sort du module : aucun réseau, aucune base.

Le résultat est volontairement prudent : en cas de doute, la réponse est "non confirmé" et la
carte prévient l'utilisateur, qui décide.
"""
from urllib.parse import urlparse

# Hébergeurs où n'importe qui peut publier sous son propre sous-domaine : une adresse qui s'y
# trouve ne prouve rien sur son auteur, même si le site officiel est sur le même hébergeur.
_HEBERGEURS_PARTAGES = (
    "github.io", "githubusercontent.com", "vercel.app", "netlify.app", "herokuapp.com",
    "pages.dev", "workers.dev", "onrender.com", "railway.app", "up.railway.app", "fly.dev",
    "ngrok.io", "ngrok-free.app", "ngrok.app", "trycloudflare.com", "loca.lt", "glitch.me",
    "replit.app", "repl.co", "azurewebsites.net", "cloudfront.net", "amazonaws.com",
    "web.app", "firebaseapp.com", "appspot.com", "supabase.co", "deno.dev", "val.run",
    "streamlit.app", "gradio.live", "hf.space", "lovable.app", "bolt.host", "modal.run",
)

# Suffixes à deux niveaux les plus courants : un site officiel ne peut pas se réduire à l'un d'eux.
_SUFFIXES_PUBLICS_DOUBLES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "co.jp", "co.nz",
    "co.in", "co.za", "com.br", "com.cn", "com.mx", "com.tr", "com.tn", "com.sg", "com.hk",
}


def hote_de(adresse: str | None) -> str | None:
    """Nom d'hôte en minuscules, sans "www." ni point final ; None si l'adresse n'en contient pas."""
    if not adresse or not isinstance(adresse, str):
        return None
    texte = adresse.strip()
    if not texte:
        return None
    if "://" not in texte:
        texte = "https://" + texte
    try:
        hote = urlparse(texte).hostname
    except ValueError:
        return None
    if not hote:
        return None
    hote = hote.rstrip(".").lower()
    if hote.startswith("www."):
        hote = hote[4:]
    return hote or None


def _sur_hebergeur_partage(hote: str) -> bool:
    return any(hote == h or hote.endswith("." + h) for h in _HEBERGEURS_PARTAGES)


def _site_utilisable(hote_site: str) -> bool:
    """Un site officiel est un vrai nom de domaine : pas une adresse IP, pas un suffixe seul."""
    if "." not in hote_site or hote_site.replace(".", "").isdigit():
        return False
    return hote_site not in _SUFFIXES_PUBLICS_DOUBLES


def adresse_du_site_officiel(adresse_serveur: str | None, site_officiel: str | None) -> bool:
    """
    Vrai seulement si l'adresse du serveur appartient au même domaine que le site officiel
    (même nom, ou l'un est un sous-domaine de l'autre) et ne se trouve pas sur un hébergeur
    partagé. Exemple : mcp.linear.app et linear.app, oui ; linear-mcp.vercel.app, non.
    """
    hote_serveur, hote_site = hote_de(adresse_serveur), hote_de(site_officiel)
    if not hote_serveur or not hote_site or not _site_utilisable(hote_site):
        return False
    if _sur_hebergeur_partage(hote_serveur) or _sur_hebergeur_partage(hote_site):
        return False
    return (
        hote_serveur == hote_site
        or hote_serveur.endswith("." + hote_site)
        or hote_site.endswith("." + hote_serveur)
    )
