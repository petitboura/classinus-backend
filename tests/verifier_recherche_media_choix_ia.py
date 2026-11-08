"""Verifie que les recherches d'image et de video laissent le modele choisir (08/11/2026).

Avant : leurs resultats portaient la cle "images" / "videos", detectee automatiquement, donc TOUT
ce que la recherche trouvait s'affichait sous le message, meme sans rapport. Maintenant : cles
"images_trouvees" / "videos_trouvees", jamais detectees, le modele ecrit ce qu'il veut montrer.
"""
import json
from unittest import mock

import core.outils_generation_media as media
from core.execution_outils import _extraire_images, _extraire_videos, _images_depuis_json_generique, _videos_depuis_json_generique

IMAGES = [{"titre": "Tour Eiffel", "url": "https://exemple.org/a.jpg", "miniature": "https://exemple.org/a_m.jpg", "credit": "X"}]
VIDEOS = [{"titre": "Histoire de la tour", "url": "https://www.youtube.com/watch?v=abcdefghijk", "miniature": "https://i.ytimg.com/a.jpg", "chaine": "C", "duree": "5:00", "id_video": "abcdefghijk"}]

# Recherche d'image : le resultat est lisible par le modele mais aucune galerie automatique.
with mock.patch.object(media, "_rechercher_images", return_value=IMAGES):
    brut = media.rechercher_image("tour eiffel")
assert json.loads(brut)["images_trouvees"] == IMAGES
assert _images_depuis_json_generique(brut) == [] and _extraire_images({}, brut) == []
assert _videos_depuis_json_generique(brut) == []

# Recherche de video : meme chose.
with mock.patch.object(media, "_rechercher_videos", return_value=VIDEOS):
    brut = media.rechercher_video("tour eiffel")
assert json.loads(brut)["videos_trouvees"] == VIDEOS
assert _videos_depuis_json_generique(brut) == [] and _extraire_videos({}, brut) == []
assert _images_depuis_json_generique(brut) == []

# Aucun resultat : message texte inchange pour le modele.
with mock.patch.object(media, "_rechercher_images", return_value=[]):
    assert "Aucune image" in media.rechercher_image("zzz")
with mock.patch.object(media, "_rechercher_videos", return_value=[]):
    assert "Aucune vid" in media.rechercher_video("zzz")

# Les autres outils (Higgsfield, captures, MCP) gardent l'affichage automatique.
autre_images = json.dumps({"images": IMAGES})
autre_videos = json.dumps({"videos": [{"titre": "v", "url": "https://exemple.org/v.mp4"}]})
assert len(_images_depuis_json_generique(autre_images)) == 1
assert len(_videos_depuis_json_generique(autre_videos)) == 1

# La consigne dit clairement que rien ne s'affiche tout seul et qu'on peut ne rien montrer.
for fonction in (media.rechercher_image, media.rechercher_video):
    doc = fonction.__doc__
    assert "RIEN ne s'affiche automatiquement" in doc and "UNIQUEMENT" in doc and "n'en place aucune" in doc
    assert "elles s'affichent quand même" not in doc and "—" not in doc and "--" not in doc

print("OK : recherche d'image et de video, le modele choisit, autres outils inchanges")
