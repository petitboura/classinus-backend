"""Verifie le bloc d'etat du canal dit au modele (16/10/2026) : active ou non, regle des cartes."""
from core.etat_canal_prompt import bloc_etat_canal

actif = bloc_etat_canal(True, True)
assert "## Canal en direct : ACTIVÉ" in actif and "DÉSACTIVÉ" not in actif
assert "https://" in actif and "cartes de vidéos et d'images" in actif and "lien complet" in actif
# Canal actif : dit meme si l'agent n'est pas Clovis (les outils du canal sont proposes des que le canal est actif).
assert bloc_etat_canal(True, False) == actif

inactif = bloc_etat_canal(False, True)
assert "## Canal en direct : DÉSACTIVÉ" in inactif and "## Canal en direct : ACTIVÉ" not in inactif
# La regle des cartes ne vaut que pour le canal actif.
assert "lien" not in inactif and "https://" not in inactif

# Agent sans canal et canal inactif : rien n'est ajoute a son prompt.
assert bloc_etat_canal(False, False) == ""

# Aucun tiret long dans les textes envoyes au modele (preference de Bourama).
for texte in (actif, inactif):
    assert "\u2014" not in texte and "--" not in texte

print("OK : etat du canal (actif, inactif, agent sans canal) et regle des cartes")
