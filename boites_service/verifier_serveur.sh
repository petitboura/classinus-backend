#!/bin/sh
# Contrôle de confinement à lancer sur le serveur Vultr, une fois le service déployé.
# Usage : BOITES_URL=https://... BOITES_TOKEN=... sh verifier_serveur.sh
set -u
H="Authorization: Bearer $BOITES_TOKEN"
ID=$(curl -s -X POST "$BOITES_URL/boites" -H "$H" -H 'Content-Type: application/json' -d '{}' | sed 's/.*"id":"\([a-f0-9]*\)".*/\1/')
echo "boîte : $ID"
run() { curl -s -X POST "$BOITES_URL/boites/$ID/commande" -H "$H" -H 'Content-Type: application/json' -d "{\"commande\":\"$1\",\"timeout\":${2:-10}}"; echo; }
echo "--- utilisateur (attendu : uid=1000)";            run "id"
echo "--- aucun secret (attendu : seulement PROXY)";    run "env | grep -i -E 'key|token|secret|password' || echo aucun"
echo "--- internet direct (attendu : échec)";           run "curl -s -m 5 https://example.com -o /dev/null -w %{http_code} --noproxy '*' || echo bloque"
echo "--- domaine non autorisé via proxy (attendu : 403)"; run "curl -s -m 5 -o /dev/null -w %{http_code} https://example.com || echo bloque"
echo "--- écriture hors dossier (attendu : refus)";     run "touch /etc/x || echo refuse"
echo "--- limite de temps (attendu : interrompu)";      run "sleep 30" 3
echo "--- bombe de processus (attendu : borné)";        run ":(){ :|:& };: ; echo fini" 5
echo "--- destruction";                                  curl -s -X DELETE "$BOITES_URL/boites/$ID" -H "$H"; echo
