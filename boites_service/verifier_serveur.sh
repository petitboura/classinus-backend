#!/bin/sh
# Contrôle de confinement à lancer sur le serveur Vultr, une fois le service déployé.
# Usage : BOITES_URL=http://localhost:8787 BOITES_TOKEN=... sh verifier_serveur.sh
set -u
H="Authorization: Bearer $BOITES_TOKEN"
ID=$(curl -s -X POST "$BOITES_URL/boites" -H "$H" -H 'Content-Type: application/json' -d '{}' | sed 's/.*"id":"\([a-f0-9]*\)".*/\1/')
echo "boîte : $ID"
case "$ID" in
  *[!a-f0-9]*|"") echo "ECHEC : la boîte n'a pas pu être créée, arrêt du test."; exit 1;;
esac
run() { curl -s -X POST "$BOITES_URL/boites/$ID/commande" -H "$H" -H 'Content-Type: application/json' -d "{\"commande\":\"$1\",\"timeout\":${2:-15}}"; echo; }
titre() { echo; echo "--- $1"; }

titre "1. utilisateur sans droits (attendu : uid=1000)";                run "id"
titre "2. aucun secret dans la boîte (attendu : seulement des noms inoffensifs, rien de Classinus ni Vultr)"; run "env | cut -d= -f1 | sort | tr '\\\\n' ' '"
titre "3. internet direct sans passer par le proxy (attendu : bloqué)"; run "curl -s -m 5 --noproxy '*' -o /dev/null -w '%{http_code}' https://example.com; echo ' (000 = bloqué)'"
titre "4. système de fichiers en lecture seule (attendu : refus)";     run "touch /etc/x 2>&1 || echo refuse"
titre "5. limite de temps (attendu : interrompu, code 124)";           run "sleep 30" 3
titre "6. limite d'espace disque (attendu : No space left on device)"; run "dd if=/dev/zero of=/home/user/gros bs=1M count=400 2>&1 | tail -1; rm -f /home/user/gros"
titre "7. limite de mémoire (attendu : tué, code=137)";                run "python -c 'x=bytearray(2*1024**3); print(1)'; echo code=\$?"

titre "9. réseau SANS autorisation : example.com via le proxy (attendu : refusé, 403)"
run "curl -sS -m 10 -o /dev/null -w '%{http_code}' https://example.com 2>&1; echo"
curl -s -X PUT "$BOITES_URL/boites/$ID/reseau" -H "$H" -H 'Content-Type: application/json' -d '{"allow_out":["example.com"]}' >/dev/null
titre "10. réseau AVEC autorisation de example.com seulement : example.com (attendu : 200)"
run "curl -sS -m 15 -o /dev/null -w '%{http_code}' https://example.com 2>&1; echo"
titre "11. même boîte, autre domaine non autorisé (attendu : refusé, 403)"
run "curl -sS -m 10 -o /dev/null -w '%{http_code}' https://www.wikipedia.org 2>&1; echo"
titre "12. adresse interne du serveur via le proxy (attendu : refusé)"
run "curl -sS -m 10 -o /dev/null -w '%{http_code}' http://169.254.169.254/ 2>&1; echo"

titre "8. bombe de processus, dans une boîte à part (attendu : nombre borné à 256 au plus)"
ID2=$(curl -s -X POST "$BOITES_URL/boites" -H "$H" -H 'Content-Type: application/json' -d '{}' | sed 's/.*"id":"\([a-f0-9]*\)".*/\1/')
curl -s -X POST "$BOITES_URL/boites/$ID2/commande" -H "$H" -H 'Content-Type: application/json' -d '{"commande":"i=0; while [ $i -lt 600 ]; do sleep 3 >/dev/null 2>&1 & i=$((i+1)); done 2>/dev/null; ls /proc | grep -c \"^[0-9]\"; echo processus-dans-la-boite","timeout":15}'; echo
curl -s -X DELETE "$BOITES_URL/boites/$ID2" -H "$H" >/dev/null

titre "destruction (la boîte ET son volume)"; curl -s -X DELETE "$BOITES_URL/boites/$ID" -H "$H"; echo
echo "Volumes restants (attendu : 0) : $(docker volume ls -q --filter label=classinus=boite 2>/dev/null | wc -l)"
