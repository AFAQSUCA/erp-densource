#!/bin/bash
# Point d'entrée du service `sauvegarde` de docker-compose.yml (audit M1-14) : lance ops/sauvegarde.sh
#   - chaque nuit à SAUVEGARDE_HEURE (défaut 02:00, fuseau TZ du conteneur) ;
#   - à la demande de l'ADMIN : le bouton « Sauvegarder maintenant » de l'ERP dépose un fichier *.demande dans
#     $SAUVEGARDE_DOSSIER/demandes (l'application n'a aucun accès à Docker ni à la base en direct).
# Pendant une sauvegarde, en_cours.json indique son début à l'écran « Sauvegardes ». Le résultat de chaque essai
# est ajouté au journal (journal.jsonl) par ops/sauvegarde.sh. Un échec n'arrête pas le service : il est consigné
# et l'essai suivant a lieu normalement.
set -euo pipefail

DOSSIER="${SAUVEGARDE_DOSSIER:-/sauvegardes}"
HEURE="${SAUVEGARDE_HEURE:-02:00}"
INTERVALLE="${SAUVEGARDE_INTERVALLE_SECONDES:-30}"
DEMANDES="$DOSSIER/demandes"

date -d "today $HEURE" > /dev/null || { echo "SAUVEGARDE_HEURE invalide : « $HEURE » (format HH:MM)" >&2; exit 1; }
mkdir -p "$DEMANDES"
chmod 1777 "$DEMANDES"  # l'application (compte non privilégié) y dépose ses demandes

prochaine() {
    local cible
    cible=$(date -d "today $HEURE" +%s)
    if [ "$cible" -le "$(date +%s)" ]; then
        cible=$(date -d "tomorrow $HEURE" +%s)
    fi
    echo "$cible"
}

lancer() {
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) Sauvegarde ($1)"
    printf '{"debut": "%s", "declencheur": "%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" > "$DOSSIER/en_cours.json"
    chmod 644 "$DOSSIER/en_cours.json"
    SAUVEGARDE_DECLENCHEUR="$1" "$(dirname "$0")/sauvegarde.sh" "$DOSSIER" || echo "Échec : consigné au journal."
    rm -f "$DOSSIER/en_cours.json"
}

rm -f "$DOSSIER/en_cours.json"  # reste d'un arrêt brutal pendant une sauvegarde
cible=$(prochaine)
echo "Service de sauvegarde prêt. Prochaine sauvegarde planifiée : $(date -d "@$cible")"
while true; do
    demande=$(find "$DEMANDES" -maxdepth 1 -type f -name '*.demande' | sort | head -n 1)
    if [ -n "$demande" ]; then
        compte=$(head -c 150 "$demande" | LC_ALL=C tr -cd '[:alnum:]._@+-')
        rm -f "$DEMANDES"/*.demande  # plusieurs demandes en attente : une seule sauvegarde suffit
        lancer "demande:${compte:-inconnu}"
    elif [ "$(date +%s)" -ge "$cible" ]; then
        lancer planifiee
        cible=$(prochaine)
    fi
    sleep "$INTERVALLE"
done
