"""
17/09/2026, demande Bourama : les aperçus de lien dans le chat (et sur
les pages de bibliothèque) ne marchaient quasiment jamais -- seul YouTube
fonctionnait (fetch direct de son oEmbed public, pas concerné ici).

Cause trouvée en creusant le code réel : components/chat/LinkPreview.tsx
(clovis-frontend) appelle `/api/apercu-lien`, une route qui n'a en fait
JAMAIS existé dans ce dépôt -- LinkPreview.tsx a été copié tel quel
depuis djiguigne-frontend le 08/08/2026 (où la route existe, sous forme
de route Next.js `app/api/apercu-lien/route.ts`), mais ce fichier de
route précis n'avait jamais été copié avec. Tout lien non-YouTube
échouait donc silencieusement (404) et retombait sur un lien texte brut.

Pourquoi ici (backend FastAPI) et pas une route Next.js dans
clovis-frontend, comme dans djiguigne-frontend : voir next.config.mjs
côté clovis-frontend -- ce dépôt n'a VOLONTAIREMENT aucune route API
Next.js, condition nécessaire pour que l'export statique (build:capacitor,
app mobile Android/iOS) continue de fonctionner. Un endpoint backend,
lui, marche identiquement pour le web ET l'app mobile (même pattern que
tout le reste du dynamique de ce produit).

Garde-fou anti-SSRF : réutilise valider_url_externe (core/securite_url.py),
déjà utilisée pour les liens lus automatiquement dans le chat
(core/lecture_urls_externes.py::_lire_url) -- même niveau de protection,
pas de nouvelle logique de sécurité inventée ici. Ne revalide pas les
redirections une à une (contrairement à la version djiguigne-frontend
d'origine) : _lire_url ne le fait pas non plus dans ce dépôt, cohérence
avec l'existant plutôt qu'un garde-fou ad hoc plus strict ici seulement.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from fastapi import APIRouter, Response

from core.securite_url import valider_url_externe, UrlNonAutorisee

router = APIRouter(prefix="/api", tags=["apercu-lien"])

DELAI_MAX_S = 5
TAILLE_MAX_OCTETS = 2 * 1024 * 1024  # 2 Mo -- largement assez pour le <head>

MOTIFS_META = {
    cle: [
        re.compile(rf'<meta[^>]+property=["\']{cle}["\'][^>]+content=["\']([^"\']*)["\']', re.I),
        re.compile(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']{cle}["\']', re.I),
        re.compile(rf'<meta[^>]+name=["\']{cle}["\'][^>]+content=["\']([^"\']*)["\']', re.I),
        re.compile(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']{cle}["\']', re.I),
    ]
    for cle in ("og:title", "og:image", "og:description", "description", "og:site_name")
}
MOTIF_TITRE = re.compile(r"<title[^>]*>([^<]*)</title>", re.I)


def _extraire_meta(html: str, cle: str) -> str | None:
    for motif in MOTIFS_META[cle]:
        trouve = motif.search(html)
        if trouve and trouve.group(1):
            return trouve.group(1)
    return None


@router.get("/apercu-lien")
def apercu_lien(url: str, response: Response):
    """
    Métadonnées Open Graph (titre, image, description, nom du site) d'une
    URL externe -- utilisé par components/chat/LinkPreview.tsx pour
    afficher un aperçu de lien au lieu d'un lien souligné brut. Pas
    d'authentification requise : un aperçu de lien n'est pas une donnée
    sensible, même principe que la bibliothèque publique.

    Renvoie {} (corps vide, jamais d'erreur HTTP) si aucune métadonnée
    n'est trouvée ou si la récupération échoue -- LinkPreview.tsx retombe
    alors sur le lien texte brut, jamais de carte cassée.
    """
    response.headers["Cache-Control"] = "public, max-age=3600"  # 1h : change rarement

    try:
        valider_url_externe(url)
    except UrlNonAutorisee as e:
        logging.warning(f"APERCU LIEN BLOQUE (SSRF) : {url} -- {e}")
        return {}

    try:
        with requests.get(
            url,
            timeout=DELAI_MAX_S,
            stream=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ClovisLinkPreview/1.0)",
                "Accept": "text/html",
            },
        ) as r:
            if not r.ok:
                return {}
            html = ""
            recu = 0
            for morceau in r.iter_content(chunk_size=8192, decode_unicode=False):
                recu += len(morceau)
                html += morceau.decode("utf-8", errors="ignore")
                if "</head>" in html.lower() or recu >= TAILLE_MAX_OCTETS:
                    break
    except Exception as e:
        logging.warning(f"APERCU LIEN ECHEC ({url}) : {e}")
        return {}

    titre = _extraire_meta(html, "og:title") or (MOTIF_TITRE.search(html).group(1) if MOTIF_TITRE.search(html) else None)
    image = _extraire_meta(html, "og:image")
    description = _extraire_meta(html, "og:description") or _extraire_meta(html, "description")
    site_name = _extraire_meta(html, "og:site_name")

    # og:image est parfois une URL relative -- rare mais arrive.
    if image and not re.match(r"^https?://", image, re.I):
        image = urljoin(url, image)

    if not titre and not image:
        return {}

    if not site_name:
        # Repli : nom d'hôte sans le "www." -- même comportement que la
        # version djiguigne-frontend d'origine quand og:site_name est absent.
        hote = urlparse(url).hostname or ""
        site_name = hote[4:] if hote.startswith("www.") else hote

    return {
        "titre": titre,
        "image": image,
        "description": description,
        "siteName": site_name,
    }
