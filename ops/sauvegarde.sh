#!/bin/bash
# Sauvegarde chiffrée de la base et des fichiers déposés (cahier-des-charges.md:282 « Sauvegardes chiffrées et
# testées » ; audit M1-14).
#
# - Base : `pg_dump` (format personnalisé, compressé).
# - Fichiers déposés (justificatifs, pièces jointes…) : archive tar.gz du dossier SAUVEGARDE_MEDIAS, si défini.
# Chacun chiffré au repos avec GPG (symétrique : une phrase de passe partagée, pas de gestion de clés). Les
# fichiers produits ne servent à rien sans elle — à conserver hors du serveur (cahier-des-charges.md:294 « offsite »).
#
# Usage :
#   DATABASE_URL=postgres://... SAUVEGARDE_PASSPHRASE=... ops/sauvegarde.sh [dossier de destination]
# En production, le service `sauvegarde` de docker-compose.yml l'appelle chaque nuit et à la demande de l'ADMIN
# (ops/planificateur-sauvegarde.sh) : aucun cron à installer.
#
# Aucun secret dans la liste des processus : phrase de passe et mot de passe de la base sont lus depuis des
# fichiers temporaires (ops/fonctions-sauvegarde.sh).
#
# Options (variables d'environnement) :
#   SAUVEGARDE_PASSPHRASE_FILE   fichier contenant la phrase de passe (à préférer à SAUVEGARDE_PASSPHRASE).
#   SAUVEGARDE_MEDIAS            dossier des fichiers déposés à sauvegarder aussi (ex. /app/media).
#   SAUVEGARDE_CONSERVER_JOURS   rotation : supprime les sauvegardes du dossier plus vieilles que N jours
#                                (défaut 30 ; 0 = ne rien supprimer). N'a lieu qu'après une sauvegarde réussie.
#   SAUVEGARDE_COPIE_RSYNC       copie hors serveur : destination rsync (ex. utilisateur@hôte:/chemin/) où
#                                les fichiers chiffrés sont envoyés juste après leur création.
#   SAUVEGARDE_JOURNAL           journal des sauvegardes, une ligne JSON par essai (défaut : journal.jsonl dans le
#                                dossier de destination), lu par l'écran « Sauvegardes ». Statut : OK ; ALERTE
#                                (sauvegarde faite mais copie hors serveur échouée) ; ECHEC (rien n'est gardé).
#   SAUVEGARDE_DECLENCHEUR       origine notée au journal (défaut « manuelle » ; « planifiee », « demande:<compte> »).
set -euo pipefail
# pipefail : sans lui, un `pg_dump` qui échoue laisserait quand même passer un fichier chiffré
# (vide ou tronqué) comme si tout s'était bien passé, `gpg` réussissant sur une entrée vide.

. "$(dirname "$0")/fonctions-sauvegarde.sh"

: "${DATABASE_URL:?DATABASE_URL doit être défini (postgres://utilisateur:motdepasse@hôte:5432/base)}"

CONSERVER_JOURS="${SAUVEGARDE_CONSERVER_JOURS:-30}"
DESTINATION="${1:-.}"
JOURNAL="${SAUVEGARDE_JOURNAL:-$DESTINATION/journal.jsonl}"
DECLENCHEUR=$(printf '%s' "${SAUVEGARDE_DECLENCHEUR:-manuelle}" | LC_ALL=C tr -cd '[:alnum:]._@+:-' | cut -c1-120)
HORODATAGE=$(date -u +%Y-%m-%dT%H-%M-%SZ)
DEBUT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
FICHIER="$DESTINATION/erp_densource_$HORODATAGE.dump.gpg"
FICHIER_MEDIAS="$DESTINATION/erp_densource_medias_$HORODATAGE.tar.gz.gpg"

# Une ligne JSON par essai : statut, message, puis la description de chaque fichier produit (ou null).
ecrire_journal() {
    printf '{"debut": "%s", "fin": "%s", "statut": "%s", "declencheur": "%s", "message": "%s", "base": %s, "medias": %s}\n' \
        "$DEBUT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$DECLENCHEUR" "$2" "$3" "$4" >> "$JOURNAL"
    chmod 644 "$JOURNAL"  # lisible par l'application, qui l'affiche à l'ADMIN
}

decrire() {
    printf '{"nom": "%s", "taille": %s, "sha256": "%s"}' \
        "$(basename "$1")" "$(stat -c %s "$1")" "$(sha256sum "$1" | cut -d' ' -f1)"
}

chiffrer() {
    gpg --batch --yes --symmetric --cipher-algo AES256 --pinentry-mode loopback \
        --passphrase-file "$SAUVEGARDE_PASSPHRASE_FILE"
}

TERMINEE=0
terminer() {
    local code=$?
    supprimer_temporaires
    if [ "$code" -ne 0 ] && [ "$TERMINEE" -eq 0 ]; then
        rm -f "$FICHIER" "$FICHIER_MEDIAS"  # jamais de fichier tronqué pris pour une sauvegarde
        ecrire_journal ECHEC "La sauvegarde a échoué (code $code) : voir les journaux du service sauvegarde." null null \
            || true
    fi
    exit "$code"
}

mkdir -p "$DESTINATION"
trap terminer EXIT
preparer_phrase_de_passe
preparer_connexion "$DATABASE_URL"

echo "Sauvegarde de la base vers $FICHIER"
pg_dump --format=custom "$URL_SANS_MOT_DE_PASSE" | chiffrer > "$FICHIER"
DESCRIPTION_BASE=$(decrire "$FICHIER")

DESCRIPTION_MEDIAS=null
if [ -n "${SAUVEGARDE_MEDIAS:-}" ]; then
    [ -d "$SAUVEGARDE_MEDIAS" ] || { echo "Dossier des fichiers introuvable : $SAUVEGARDE_MEDIAS" >&2; exit 1; }
    echo "Sauvegarde des fichiers déposés ($SAUVEGARDE_MEDIAS) vers $FICHIER_MEDIAS"
    tar -C "$SAUVEGARDE_MEDIAS" -czf - . | chiffrer > "$FICHIER_MEDIAS"
    DESCRIPTION_MEDIAS=$(decrire "$FICHIER_MEDIAS")
fi

echo "Empreintes SHA-256 (à noter pour vérifier l'intégrité avant restauration) :"
sha256sum "$FICHIER" ${SAUVEGARDE_MEDIAS:+"$FICHIER_MEDIAS"}

STATUT=OK
MESSAGE="Sauvegarde réussie."
if [ -n "${SAUVEGARDE_COPIE_RSYNC:-}" ]; then
    echo "Copie hors serveur vers $SAUVEGARDE_COPIE_RSYNC"
    # La sauvegarde locale est bonne même si la copie échoue : on la garde, mais l'ADMIN est alerté.
    if ! rsync -a "$FICHIER" ${SAUVEGARDE_MEDIAS:+"$FICHIER_MEDIAS"} "$SAUVEGARDE_COPIE_RSYNC"; then
        STATUT=ALERTE
        MESSAGE="Sauvegarde faite sur ce serveur, mais la copie hors serveur a échoué : à vérifier."
    fi
fi

ecrire_journal "$STATUT" "$MESSAGE" "$DESCRIPTION_BASE" "$DESCRIPTION_MEDIAS"
TERMINEE=1
echo "$STATUT : $(du -h "$FICHIER" | cut -f1) (base)${SAUVEGARDE_MEDIAS:+, $(du -h "$FICHIER_MEDIAS" | cut -f1) (fichiers)}"

if [ "$CONSERVER_JOURS" -gt 0 ]; then
    # Rotation : seulement les sauvegardes de ce script (même préfixe), seulement après une réussite. Un échec
    # ici ne remet pas en cause la sauvegarde qui vient d'être faite.
    find "$DESTINATION" -maxdepth 1 -name 'erp_densource_*.gpg' -mtime +"$CONSERVER_JOURS" -print -delete \
        || echo "Rotation impossible (sauvegarde conservée)." >&2
fi
