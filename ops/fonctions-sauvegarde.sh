#!/bin/bash
# Fonctions communes à ops/sauvegarde.sh et ops/restauration.sh (à inclure avec « . », jamais à exécuter).
#
# Aucun secret n'apparaît dans la liste des processus (visible de tous les comptes du serveur) : la phrase de passe
# GPG et le mot de passe de la base sont lus depuis des fichiers temporaires (droits 600), supprimés en sortie.

umask 077
TEMPORAIRES=()

supprimer_temporaires() {
    if [ "${#TEMPORAIRES[@]}" -gt 0 ]; then
        rm -f "${TEMPORAIRES[@]}"
    fi
}

# Fichier de la phrase de passe GPG : SAUVEGARDE_PASSPHRASE_FILE s'il est fourni (à préférer), sinon un fichier
# temporaire fabriqué à partir de SAUVEGARDE_PASSPHRASE.
preparer_phrase_de_passe() {
    if [ -z "${SAUVEGARDE_PASSPHRASE_FILE:-}" ]; then
        : "${SAUVEGARDE_PASSPHRASE:?SAUVEGARDE_PASSPHRASE (ou SAUVEGARDE_PASSPHRASE_FILE) doit être défini : phrase de passe de chiffrement}"
        SAUVEGARDE_PASSPHRASE_FILE=$(mktemp)
        TEMPORAIRES+=("$SAUVEGARDE_PASSPHRASE_FILE")
        printf '%s' "$SAUVEGARDE_PASSPHRASE" > "$SAUVEGARDE_PASSPHRASE_FILE"
    fi
}

# Retire le mot de passe de l'URL (postgres://utilisateur:motdepasse@hôte:port/base) : URL_SANS_MOT_DE_PASSE est
# passée à pg_dump / pg_restore, le mot de passe va dans un fichier .pgpass temporaire (PGPASSFILE). Les « %XX » de
# l'URL sont décodés ; « : » et « \ » sont échappés comme l'exige le format .pgpass.
preparer_connexion() {
    URL_SANS_MOT_DE_PASSE="$1"
    local motif='^(postgres(ql)?://)([^:@/]*):([^@]*)@(.*)$'
    if [[ "$1" =~ $motif ]]; then
        URL_SANS_MOT_DE_PASSE="${BASH_REMATCH[1]}${BASH_REMATCH[3]}@${BASH_REMATCH[5]}"
        local brut="${BASH_REMATCH[4]}" mot_de_passe
        brut="${brut//\\/\\\\}"  # un « \ » du mot de passe reste un « \ » (printf %b n'interprète que les %XX)
        mot_de_passe=$(printf '%b' "${brut//%/\\x}")
        PGPASSFILE=$(mktemp)
        TEMPORAIRES+=("$PGPASSFILE")
        printf '*:*:*:*:%s\n' "$(printf '%s' "$mot_de_passe" | sed -e 's/\\/\\\\/g' -e 's/:/\\:/g')" > "$PGPASSFILE"
        export PGPASSFILE
    fi
}
